"""Pydantic schemas for user management."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    roles: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            raise ValueError("Invalid email address")
        return cleaned


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class UserRolesUpdate(BaseModel):
    roles: list[str] = Field(..., min_length=0)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

