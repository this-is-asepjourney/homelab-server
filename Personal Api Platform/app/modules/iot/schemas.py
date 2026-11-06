"""Pydantic schemas for IoT devices, credentials, telemetry, and commands."""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    project_id: uuid.UUID
    device_uid: str = Field(..., min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-_:]*$")
    name: str = Field(default="", max_length=255)
    device_type: str = Field(default="esp32", min_length=2, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = Field(default=None, pattern=r"^(registered|online|offline|maintenance|disabled)$")
    metadata: Optional[dict[str, Any]] = None


class DeviceRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    device_uid: str
    name: str
    device_type: str
    status: str
    metadata: dict[str, Any]
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DeviceRegisteredResponse(DeviceRead):
    raw_credential: str


class CredentialRotationResponse(BaseModel):
    device_id: uuid.UUID
    device_uid: str
    credential_id: uuid.UUID
    raw_credential: str
    rotated_at: datetime


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., min_length=2, max_length=128)
    timestamp: datetime
    temperature: Optional[float] = Field(default=None, ge=-100.0, le=1000.0)
    counter: Optional[int] = Field(default=None, ge=0)
    current: Optional[float] = Field(default=None, ge=0.0, le=500.0)
    extra: dict[str, Any] = Field(default_factory=dict)


class TelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    device_uid: str
    timestamp: datetime
    temperature: Optional[float] = None
    counter: Optional[int] = None
    current: Optional[float] = None
    payload: dict[str, Any]
    created_at: datetime


class CommandCreate(BaseModel):
    command: str = Field(..., min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9_.\-]+$")
    parameters: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = Field(default=None, max_length=128)
    ttl_seconds: int = Field(default=300, ge=5, le=86400)


class CommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    correlation_id: str
    command: str
    parameters: dict[str, Any]
    status: str
    expires_at: datetime
    acknowledged_at: Optional[datetime] = None
    created_at: datetime

