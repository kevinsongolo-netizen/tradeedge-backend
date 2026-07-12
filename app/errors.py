"""Application exception hierarchy + global handlers.

Per Section 11 of the Sprint 6 architecture spec:

* Routers never raise these directly (they delegate to services).
* Services raise ``AppError`` subclasses; they never let raw SQLAlchemy
  exceptions escape (repositories wrap those first).
* Engines raise plain ``ValueError`` on truly impossible input and know
  nothing about HTTP.

Every ``AppError`` is rendered as the same RFC-7807-ish envelope:
``{"error": {"code", "message", "details", "request_id"}}``.
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger("tradeedge")


class AppError(Exception):
    """Base class for all application-raised errors."""

    code = "APP_ERROR"
    status = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status = 422


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status = 404


class ConflictError(AppError):
    code = "CONFLICT"
    status = 409


class AuthError(AppError):
    code = "AUTH"
    status = 401


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status = 403


class EngineError(AppError):
    code = "ENGINE_ERROR"
    status = 500


class DatasetError(AppError):
    code = "DATASET_ERROR"
    status = 400


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _envelope(code: str, message: str, details: Any, request_id: str | None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Wires the global exception handlers onto the FastAPI app. Called
    once from ``app.main.create_app``."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.error(
            "app_error",
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
        )
        return JSONResponse(
            status_code=exc.status,
            content=_envelope(exc.code, exc.message, exc.details, _request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": exc.errors()},
                _request_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", request_id=_request_id(request))
        return JSONResponse(
            status_code=500,
            content=_envelope(
                "INTERNAL", "An unexpected error occurred", None, _request_id(request)
            ),
        )
