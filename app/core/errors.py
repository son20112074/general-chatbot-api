"""AppError + exception handlers for structured error responses."""
from typing import NoReturn

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Application error with a stable machine-readable code.

    Raise this anywhere in services or endpoints. The global exception
    handler converts it to a structured JSON response.
    """

    def __init__(self, code: str, detail: str, status: int = 400):
        self.code = code
        self.detail = detail
        self.status = status
        super().__init__(detail)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={
            "detail": exc.detail,
            "message": exc.detail,
            "code": exc.code,
            "status": exc.status,
        },
    )


async def http_exception_to_app(_request: Request, exc: HTTPException) -> JSONResponse:
    """Make legacy HTTPException responses match the AppError shape.

    If `exc.detail` is a dict/list, pass it through unchanged so the frontend
    receives the structured form instead of a stringified repr. `message`
    mirrors `detail` as a string so FE can read a consistent top-level
    field across all error responses.
    """
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": detail,
            "message": message,
            "code": f"HTTP_{exc.status_code}",
            "status": exc.status_code,
        },
    )


def raise_app_error(entry: tuple[str, str], status: int = 400, **fmt) -> NoReturn:
    """Raise an AppError from a (CODE, MSG) tuple in error_messages.

    Pass keyword args to fill `{name}` placeholders in the message template.

    Example:
        raise_app_error(PARENT_FOLDER_NOT_FOUND, status=400, parent_id=42)
    """
    code, message = entry
    raise AppError(
        code=code,
        detail=message.format(**fmt) if fmt else message,
        status=status,
    )
