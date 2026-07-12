"""Structured logging setup.

Configures structlog to emit JSON logs to stdout, and provides a
Starlette middleware that logs every request/response pair with a
correlation id and execution time. This is the only place logging is
configured — engines, services, and routers just call
``structlog.get_logger(__name__)`` and inherit this setup.
"""
import logging
import sys
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings

logger = structlog.get_logger("tradeedge")


def configure_logging() -> None:
    """Wire structlog on top of stdlib logging so third-party libraries
    (uvicorn, sqlalchemy) end up in the same JSON stream."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestLoggingMiddleware:
    """Logs ``request.received`` / ``request.completed`` (or
    ``request.failed``) for every call, each tagged with a per-request
    UUID that is also bound to any logs emitted deeper in the call stack
    (services, engines) and returned via the ``X-Request-ID`` header.

    Implemented as a plain ASGI middleware (rather than
    ``starlette.middleware.base.BaseHTTPMiddleware``). ``BaseHTTPMiddleware``
    runs the downstream app in a separate task and hands the response back
    over an in-memory stream; under certain Starlette/anyio versions that
    hand-off can deadlock when the app is driven synchronously — which is
    exactly what ``fastapi.testclient.TestClient`` does. That deadlock is
    what caused the backend test suite to hang indefinitely. A pure ASGI
    middleware talks directly to ``receive``/``send`` with no extra task or
    stream in between, so there's nothing to deadlock on.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        method = scope.get("method", "")
        path = scope.get("path", "")

        # Exposed via Request.state.request_id so exception handlers
        # (app/errors.py) can include it in the error envelope.
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        logger.info("request.received", method=method, path=path)

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request.failed",
                method=method,
                path=path,
                duration_ms=duration_ms,
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request.completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
