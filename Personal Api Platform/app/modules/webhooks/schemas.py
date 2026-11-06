"""Pydantic schemas for webhook subscriptions and deliveries."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class WebhookCreate(BaseModel):
    project_id: uuid.UUID
    event_type: str = Field(..., min_length=3, max_length=128)
    target_reference: str = Field(..., min_length=4, max_length=512)
    secret_reference: Optional[str] = Field(default=None, max_length=128)


class WebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    target_reference: str
    secret_reference: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID
    event_id: str
    status: str
    attempt_count: int
    response_code: Optional[int] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

