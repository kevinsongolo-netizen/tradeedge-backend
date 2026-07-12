"""Declarative base for all SQLAlchemy ORM models.

Step 2 scope: no models are defined yet (that lands starting Step 3 —
Trade CRUD). This module just provides the shared ``Base`` class every
future model inherits from, plus a consistent constraint-naming
convention so that Alembic (wired up in a later, separate step)
autogenerates predictable constraint names (``ix_...``, ``uq_...``,
``fk_...``) instead of driver-default ones that differ between SQLite
and Postgres.
"""
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Applied to every table's metadata so generated constraint names are
# deterministic and identical across SQLite (dev) and Postgres (prod).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base. All future ORM models
    (``app/db/models/*.py``) inherit from this."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
