"""FastAPI dependency wiring shared by every router.

Sprint 6 has no auth wall (Section 12 of the architecture spec):
``get_current_user_id`` reads the optional ``X-User-Id`` header and
falls back to the seeded user (``id=1``). Sprint 8 will replace the
header check with real JWT verification without changing any router
signature — everything already depends on a plain ``int`` user id.
"""
from __future__ import annotations

from fastapi import Header

from app.db.session import get_db_session

DEFAULT_USER_ID = 1


async def get_current_user_id(x_user_id: int | None = Header(default=None)) -> int:
    """Resolves the "current user" for a request.

    Sprint 6: single local user, no auth. ``X-User-Id`` is accepted (and
    used by tests to simulate multiple users against the same seeded
    schema) but defaults to ``1`` — the row seeded by the initial
    migration. Sprint 8 replaces this with ``Authorization: Bearer``
    JWT verification; every service already takes a plain ``user_id``
    so no other code changes.
    """
    return x_user_id if x_user_id is not None else DEFAULT_USER_ID


__all__ = ["get_db_session", "get_current_user_id", "DEFAULT_USER_ID"]
