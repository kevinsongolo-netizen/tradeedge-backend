"""Sprint 7 — CLI entry point to train the first ML model version.

Referenced by ``app/db/models/ml_export.py``'s Sprint 6 docstring
("no rows are written until Sprint 7's ``scripts/train_v1.py``
exists"). Runs the exact same ``MLTrainingService.train()`` the
``POST /api/v1/ml/train`` endpoint calls, so a CLI-trained model and an
API-trained model are byte-for-byte the same code path.

Usage:
    python scripts/train_v1.py                  # trains for user 1 (default seed user)
    python scripts/train_v1.py --user-id 2
    python scripts/train_v1.py --report-only     # just prints the Phase 1 validation report
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import get_sessionmaker  # noqa: E402
from app.services.ml_training_service import InsufficientDataError, MLTrainingService  # noqa: E402


async def run(user_id: int, report_only: bool) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        service = MLTrainingService(session)

        report = await service.validation_report(user_id)
        print("=== Phase 1: Dataset validation report ===")
        print(json.dumps(report, indent=2))

        if report_only:
            return

        if not report["readyForTraining"]:
            print(f"\nNot training: {report['reason']}")
            return

        print("\n=== Phase 3/4: Training + comparing models ===")
        try:
            result = await service.train(user_id)
        except InsufficientDataError as exc:
            print(f"Training aborted: {exc}")
            return

        print(json.dumps(result, indent=2, default=str))
        print(
            f"\nTrained {result['algorithm']} ({result['version']}) on "
            f"{result['rowsUsed']} trades. Test-set accuracy: "
            f"{result['testMetrics']['accuracy']:.3f}, ROC AUC: "
            f"{result['testMetrics']['rocAuc']}."
        )
        if result["overfitWarning"]:
            print(
                "WARNING: train/test accuracy gap suggests possible overfitting — "
                "treat predictions cautiously until more trades accumulate."
            )
        print(f"Model saved to: {result['modelPath']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the TradeEdge AI ML model (Sprint 7, v1).")
    parser.add_argument("--user-id", type=int, default=1, help="User id to train for (default: 1).")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only print the Phase 1 validation report; do not train.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.user_id, args.report_only))


if __name__ == "__main__":
    main()
