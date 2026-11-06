"""Pydantic schemas for user login, M2M client credentials, refresh tokens, and sessions."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class ClientCredentialsRequest(BaseModel):
    client_id: str = Field(..., min_length=2, max_length=128)
    client_secret: str = Field(..., min_length=8, max_length=256)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(default=None, max_length=512)
    revoke_all: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int
    session_id: Optional[uuid.UUID] = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime

