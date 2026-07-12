"""Pydantic v2 schemas — the public API contract (Section 4 of the
architecture spec). SQLAlchemy models never leak into responses;
everything crossing the HTTP boundary goes through one of these.
"""
