"""Pydantic schemas for project registration and membership management."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="active", pattern=r"^(active|inactive|archived)$")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive|archived)$")


class ProjectMembershipCreate(BaseModel):
    user_id: uuid.UUID
    membership_role: str = Field(default="member", min_length=2, max_length=64)


class ProjectMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    membership_role: str
    created_at: datetime


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

