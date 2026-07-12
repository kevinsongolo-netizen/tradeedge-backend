"""Repository classes that wrap SQLAlchemy queries for services to call.

All SQL lives here — services never see SQLAlchemy directly (Section
5.1 of the Sprint 6 architecture spec).
"""
from app.db.repositories.analysis_repo import AnalysisRepository
from app.db.repositories.ml_export_repo import MLExportRepository
from app.db.repositories.trade_repo import TradeRepository
from app.db.repositories.user_repo import UserRepository
from app.db.repositories.weights_repo import WeightsRepository

__all__ = [
    "TradeRepository",
    "AnalysisRepository",
    "UserRepository",
    "WeightsRepository",
    "MLExportRepository",
]
