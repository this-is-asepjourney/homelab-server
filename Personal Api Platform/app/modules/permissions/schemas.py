"""Pydantic schemas for roles, permissions, and scopes."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ScopeCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-z0-9_]+:[a-z0-9_]+$")
    description: str = Field(default="", max_length=255)


class ScopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    created_at: datetime


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    created_at: datetime


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RolePermissionsUpdate(BaseModel):
    permissions: list[str] = Field(..., min_length=0)


class RoleRead(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime

