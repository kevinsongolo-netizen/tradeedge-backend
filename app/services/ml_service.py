"""ML Service — Section 5.2's ``build``, ``validate``, ``export_json``,
``export_csv``, ``stream_csv``.

Builds the leakage-safe ML training dataset from a user's full trade +
analysis history, validates it, and writes JSON/CSV artifacts to
``EXPORT_DIR`` while recording an audit row in ``ml_exports`` (Section
9.5's export flow).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories.ml_export_repo import MLExportRepository
from app.db.repositories.trade_repo import TradeRepository
from app.engines.ml_dataset import ML_DATASET_VERSION, build_dataset, to_csv, validate_dataset


class MLService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.trade_repo = TradeRepository(session)
        self.export_repo = MLExportRepository(session)
        self.settings = get_settings()

    async def build(self, user_id: int) -> list[dict[str, Any]]:
        """build(user_id) — flattens the user's full history into
        ML-ready rows (both valid and rejected; callers filter as
        needed)."""
        trades = await self.trade_repo.list_all_with_analyses(user_id)
        entries = [t.to_engine_dict() for t in trades]
        exported_at = datetime.now(timezone.utc).isoformat()
        return build_dataset(entries, exported_at=exported_at, user_id=user_id)

    async def validate(self, user_id: int) -> dict:
        """validate(user_id) — ``GET /ml/validate``: per-row validation
        report + overall quality score, without writing any file."""
        rows = await self.build(user_id)
        return validate_dataset(rows)

    async def dataset_json(self, user_id: int, *, valid_only: bool = True) -> list[dict[str, Any]]:
        rows = await self.build(user_id)
        if valid_only:
            rows = [r for r in rows if r["validation_status"] == "valid"]
        return rows

    async def dataset_csv(self, user_id: int, *, valid_only: bool = True) -> str:
        rows = await self.dataset_json(user_id, valid_only=valid_only)
        return to_csv(rows)

    async def export(self, user_id: int, fmt: str = "both") -> dict:
        """export(user_id, format) — Section 9.5's export flow: build,
        validate, write JSON and/or CSV to ``EXPORT_DIR``, record an
        ``ml_exports`` audit row with a sha256 checksum, and return the
        summary + file list."""
        rows = await self.build(user_id)
        report = validate_dataset(rows)
        valid_rows = [r for r in rows if r["validation_status"] == "valid"]

        export_dir = Path(self.settings.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).date().isoformat()
        files: list[dict[str, str]] = []

        if fmt in ("json", "both"):
            json_path = export_dir / f"tradeedge-ml-dataset-{stamp}-v{ML_DATASET_VERSION}.json"
            content = json.dumps(valid_rows, indent=2, default=str)
            json_path.write_text(content, encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            files.append({"format": "json", "path": str(json_path), "checksum": checksum})
            await self.export_repo.insert(
                user_id,
                {
                    "format": "json",
                    "row_count": len(valid_rows),
                    "rejected_count": report["invalidCount"],
                    "quality_score": report["qualityScore"],
                    "dataset_version": ML_DATASET_VERSION,
                    "file_path": str(json_path),
                    "checksum": checksum,
                },
            )

        if fmt in ("csv", "both"):
            csv_path = export_dir / f"tradeedge-ml-dataset-{stamp}-v{ML_DATASET_VERSION}.csv"
            content = to_csv(valid_rows)
            csv_path.write_text(content, encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            files.append({"format": "csv", "path": str(csv_path), "checksum": checksum})
            await self.export_repo.insert(
                user_id,
                {
                    "format": "csv",
                    "row_count": len(valid_rows),
                    "rejected_count": report["invalidCount"],
                    "quality_score": report["qualityScore"],
                    "dataset_version": ML_DATASET_VERSION,
                    "file_path": str(csv_path),
                    "checksum": checksum,
                },
            )

        await self.session.commit()
        return {
            "rowCount": len(valid_rows),
            "rejectedCount": report["invalidCount"],
            "qualityScore": report["qualityScore"],
            "datasetVersion": ML_DATASET_VERSION,
            "files": files,
        }
