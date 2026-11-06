"""Pydantic schemas for API clients, hashed API keys, and scope assignment."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ApiClientCreate(BaseModel):
    project_id: uuid.UUID
    client_id: str = Field(..., min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-_.]*$")
    name: str = Field(..., min_length=2, max_length=255)
    client_type: str = Field(default="backend", pattern=r"^(backend|service|iot|admin)$")
    client_secret: Optional[str] = Field(default=None, min_length=8, max_length=256)
    scopes: list[str] = Field(default_factory=list)


class ClientScopesUpdate(BaseModel):
    scopes: list[str] = Field(default_factory=list)


class ApiKeyCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=128)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    key_prefix: str
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime


class ApiKeyIssuedResponse(ApiKeyRead):
    raw_key: str


class ApiClientRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    client_id: str
    name: str
    client_type: str
    is_active: bool
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

