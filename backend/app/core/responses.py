"""Uniform response envelope.

Every endpoint returns the same shape the reference Node service returned, so
existing API consumers and the frontend `ApiService` need no translation layer:

    { "message": str, "status": bool, "code": int, "data": Any }
    { "message": str, "status": bool, "code": int, "error": Any }
"""

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.status_codes import StatusCode


def success_body(
    message: str = "Success.",
    data: Any = None,
    code: int = StatusCode.OK,
    status: bool = True,
) -> dict:
    return {"message": message, "status": status, "code": int(code), "data": data}


def error_body(
    message: str = "Something went wrong.",
    errors: Any = None,
    code: int = StatusCode.INTERNAL_SERVER_ERROR,
) -> dict:
    return {"message": message, "status": False, "code": int(code), "error": errors}


def ok(
    message: str = "Success.",
    data: Any = None,
    code: int = StatusCode.OK,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=int(code),
        content=jsonable_encoder(success_body(message, data, code, status=True)),
        headers=headers,
    )


def fail(
    message: str,
    code: int = StatusCode.BAD_REQUEST,
    data: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """A handled, non-exceptional negative outcome.

    `status` is False but the payload still uses the `data` key, matching the
    reference service's `success(false, ...)` calls.
    """
    return JSONResponse(
        status_code=int(code),
        content=jsonable_encoder(success_body(message, data, code, status=False)),
        headers=headers,
    )


def error(
    message: str,
    errors: Any = None,
    code: int = StatusCode.INTERNAL_SERVER_ERROR,
) -> JSONResponse:
    return JSONResponse(
        status_code=int(code), content=error_body(message, errors, code)
    )
