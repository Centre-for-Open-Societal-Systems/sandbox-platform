"""Domain exceptions and the handlers that render them as the response envelope."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.responses import error, fail
from app.core.status_codes import StatusCode

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for expected, user-facing failures."""

    status_code: int = StatusCode.BAD_REQUEST
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        data: Any = None,
        status_code: int | None = None,
    ):
        self.message = message or self.message
        self.data = data
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = StatusCode.NOT_FOUND
    message = "Record not found."


class ValidationError(AppError):
    status_code = StatusCode.BAD_REQUEST
    message = "Validation failed."


class UnauthorizedError(AppError):
    status_code = StatusCode.UNAUTHORIZED
    message = "Unauthorized."


class ForbiddenError(AppError):
    status_code = StatusCode.FORBIDDEN
    message = "You do not have permission to perform this action."


class ConflictError(AppError):
    status_code = StatusCode.CONFLICT
    message = "Record already exists."


class UpstreamError(AppError):
    status_code = StatusCode.BAD_GATEWAY
    message = "Upstream service is unavailable."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return fail(exc.message, code=exc.status_code, data=exc.data)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "message": err.get("msg", ""),
            }
            for err in exc.errors()
        ]
        first = details[0]["message"] if details else "Invalid request payload."
        return error(first, errors=details, code=StatusCode.BAD_REQUEST)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return fail(str(exc.detail), code=exc.status_code)

    @app.exception_handler(SQLAlchemyOperationalError)
    @app.exception_handler(SQLAlchemyTimeoutError)
    async def _database_unavailable(request: Request, exc: Exception):
        # Connection refused, pool exhausted, server restarting: tell the
        # client to retry rather than reporting a bug.
        logger.error(
            "Database unavailable on %s %s: %s",
            request.method,
            request.url.path,
            exc.__class__.__name__,
        )
        return error(
            "The service is temporarily unavailable, please try again shortly.",
            code=StatusCode.SERVICE_UNAVAILABLE,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error("Internal server error.", code=StatusCode.INTERNAL_SERVER_ERROR)
