"""Application exceptions and FastAPI exception handlers."""

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_request_id, logger, redact_value


class PAPException(Exception):
    """Base exception for Personal API Platform."""

    def __init__(
        self,
        message: str,
        code: str = "ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class BadRequestError(PAPException):
    def __init__(self, message: str = "Bad request", code: str = "BAD_REQUEST", details: Any = None) -> None:
        super().__init__(message=message, code=code, status_code=status.HTTP_400_BAD_REQUEST, details=details)


class AuthenticationError(PAPException):
    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "AUTHENTICATION_FAILED",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status.HTTP_401_UNAUTHORIZED, details=details)


class PermissionDeniedError(PAPException):
    def __init__(
        self,
        message: str = "Permission denied",
        code: str = "INSUFFICIENT_SCOPE",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status.HTTP_403_FORBIDDEN, details=details)


class NotFoundError(PAPException):
    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "RESOURCE_NOT_FOUND",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status.HTTP_404_NOT_FOUND, details=details)


class ConflictError(PAPException):
    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "RESOURCE_CONFLICT",
        details: Any = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status.HTTP_409_CONFLICT, details=details)


class RateLimitExceededError(PAPException):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        code: str = "RATE_LIMIT_EXCEEDED",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class ServiceUnavailableError(PAPException):
    def __init__(
        self,
        message: str = "Downstream service or feature unavailable",
        code: str = "SERVICE_UNAVAILABLE",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


def build_error_payload(message: str, code: str, details: Any = None) -> dict[str, Any]:
    return {
        "success": False,
        "message": message,
        "error": {
            "code": code,
            "details": redact_value(details) if details is not None else None,
        },
        "meta": {
            "api_version": "v1",
            "request_id": get_request_id(),
        },
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PAPException)
    async def pap_exception_handler(request: Request, exc: PAPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(exc.message, exc.code, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized_errors = []
        for err in exc.errors():
            sanitized_errors.append(
                {
                    "loc": list(err.get("loc", [])),
                    "msg": err.get("msg", "Invalid value"),
                    "type": err.get("type", "value_error"),
                }
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=build_error_payload(
                message="Request validation failed",
                code="VALIDATION_ERROR",
                details=sanitized_errors,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "PERMISSION_DENIED",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMIT_EXCEEDED",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(str(exc.detail), code, None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {type(exc).__name__}",
            exc_info=False,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error_payload(
                message="Internal server error",
                code="INTERNAL_SERVER_ERROR",
                details=None,
            ),
        )

