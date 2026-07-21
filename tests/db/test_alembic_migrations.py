"""Alembic migration sanity checks.

Added after a real production deploy failure (Sprint 22 follow-up):
migration 0008's revision id was 39 characters
("0008_drop_redundant_live_snapshot_index"). Alembic's own
``alembic_version`` bookkeeping table types ``version_num`` as
``VARCHAR(32)`` -- a hard limit Alembic itself enforces via the DB
driver, not something this project chose. SQLite doesn't enforce
VARCHAR length at all, so this passed every local test and a full
`alembic upgrade head` dry run against a fresh SQLite database, then
failed on deploy against the real Postgres database with
``StringDataRightTruncationError`` the moment Alembic tried to record
that the migration had completed -- by which point the migration's own
schema changes may already have run (Postgres DDL is transactional, so
in this case they rolled back together, but that's not guaranteed in
every DB/config). This test exists so a future long revision id is
caught locally before it ever reaches a deploy, regardless of which
database engine local testing happens to use.
"""
import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

#: Alembic's own alembic_version.version_num column width -- not
#: configurable per-project without a custom env.py override, which
#: this project doesn't do.
ALEMBIC_VERSION_NUM_MAX_LENGTH = 32


def _revision_ids() -> dict[str, str]:
    """Parses ``revision: str = "..."`` out of every migration file
    without importing them (avoids needing every migration's runtime
    dependencies just to read a string constant)."""
    ids: dict[str, str] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text()
        match = re.search(r'^revision(?:\s*:\s*[^=]+)?\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert match, f"Could not find a revision id in {path.name}"
        ids[path.name] = match.group(1)
    return ids


def test_every_migration_file_exists():
    assert VERSIONS_DIR.is_dir()
    assert list(VERSIONS_DIR.glob("*.py"))


def test_every_revision_id_fits_in_alembic_version_num_column():
    ids = _revision_ids()
    assert ids, "no migrations found to check"
    too_long = {
        filename: revision
        for filename, revision in ids.items()
        if len(revision) > ALEMBIC_VERSION_NUM_MAX_LENGTH
    }
    assert not too_long, (
        f"Revision id(s) exceed Postgres's alembic_version.version_num "
        f"VARCHAR({ALEMBIC_VERSION_NUM_MAX_LENGTH}) limit -- would pass "
        f"locally against SQLite (no length enforcement) but fail on "
        f"deploy against Postgres: {too_long}"
    )


def test_revision_ids_are_unique():
    ids = list(_revision_ids().values())
    assert len(ids) == len(set(ids)), "duplicate revision ids found across migration files"
