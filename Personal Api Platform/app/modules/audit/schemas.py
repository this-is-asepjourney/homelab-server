"""Pydantic schemas for audit logs."""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    action: str
    resource: str
    resource_id: Optional[str] = None
    status: str
    ip_address: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    created_at: datetime

