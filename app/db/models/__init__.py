"""ORM models package.

Every model must be imported here so it registers on ``Base.metadata``
before Alembic autogenerate or ``Base.metadata.create_all`` runs (used
by the test suite's in-memory SQLite fixtures).
"""
from app.db.models.account_margin import AccountMargin
from app.db.models.ai_analysis import AIAnalysis
from app.db.models.live_snapshot import LiveSnapshot
from app.db.models.ml_export import MLExport, MLModel
from app.db.models.trade import Trade
from app.db.models.user import User
from app.db.models.weights import ScoringWeights

__all__ = [
    "User",
    "Trade",
    "AIAnalysis",
    "ScoringWeights",
    "MLExport",
    "MLModel",
    "LiveSnapshot",
    "AccountMargin",
]
