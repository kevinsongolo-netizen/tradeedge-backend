"""Shared Pydantic building blocks: the CamelModel base and enums.

Every public schema inherits from ``CamelModel`` so JSON in/out uses
camelCase (matching the JS engines' field names, per Section 6.1 of the
architecture spec: "Casing preserved in output payloads") while Python
code still uses idiomatic snake_case attribute names.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: snake_case in Python, camelCase over the wire.

    ``populate_by_name`` lets code construct instances with either the
    Python name or the camelCase alias; ``from_attributes`` lets these
    models be built directly from ORM rows.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Direction(str, Enum):
    buy = "buy"
    sell = "sell"


class AssetClass(str, Enum):
    forex = "Forex"
    crypto = "Crypto"
    index = "Index"
    metal = "Metal"


class SessionName(str, Enum):
    asian = "Asian"
    london = "London"
    new_york = "New York"
    overlap = "Overlap"


class H4Trend(str, Enum):
    bullish = "Bullish"
    bearish = "Bearish"
    ranging = "Ranging"


class PremiumDiscount(str, Enum):
    premium = "Premium"
    discount = "Discount"
    equilibrium = "Equilibrium"


class NewsImpact(str, Enum):
    none = "None"
    low = "Low"
    medium = "Medium"
    high = "High"


class FollowedPlan(str, Enum):
    yes = "Yes"
    partial = "Partial"
    no = "No"


class Emotion(str, Enum):
    calm = "Calm"
    confident = "Confident"
    fomo = "FOMO"
    revenge = "Revenge"
    anxious = "Anxious"
    bored = "Bored"


class Recommendation(str, Enum):
    take = "TAKE"
    caution = "CAUTION"
    skip = "SKIP"


class ExecutionGrade(str, Enum):
    excellent = "EXCELLENT"
    good = "GOOD"
    fair = "FAIR"
    poor = "POOR"


class Outcome(str, Enum):
    win = "Win"
    loss = "Loss"
    breakeven = "Breakeven"


class QualityBucket(str, Enum):
    a = "A"
    b = "B"
    c = "C"
    d = "D"


class ErrorDetail(CamelModel):
    """RFC-7807-ish error envelope body (Section 11.1/11.2)."""

    code: str
    message: str
    details: dict | None = None
    request_id: str | None = None


class ErrorResponse(CamelModel):
    error: ErrorDetail
