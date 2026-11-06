"""Shared API response envelope and pagination schemas."""

from typing import Any, Generic, Optional, TypeVar
import uuid

from pydantic import BaseModel, Field

from app.core.logging import get_request_id

T = TypeVar("T")


class ResponseMeta(BaseModel):
    api_version: str = "v1"
    request_id: str = Field(default_factory=get_request_id)
    page: Optional[int] = None
    page_size: Optional[int] = None
    total: Optional[int] = None


class ErrorDetail(BaseModel):
    code: str
    details: Optional[Any] = None


class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[T] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: ErrorDetail
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


def success_response(
    data: Any = None,
    message: str = "Data retrieved successfully",
    *,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    total: Optional[int] = None,
) -> dict[str, Any]:
    """Construct a standard PAP v1 success response dictionary."""
    meta: dict[str, Any] = {
        "api_version": "v1",
        "request_id": get_request_id() or str(uuid.uuid4()),
    }
    if page is not None:
        meta["page"] = page
    if page_size is not None:
        meta["page_size"] = page_size
    if total is not None:
        meta["total"] = total

    return {
        "success": True,
        "message": message,
        "data": data,
        "meta": meta,
    }

