"""HTTP router for webhook subscriptions and delivery state."""

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_any_scope
from app.modules.webhooks.schemas import (
    WebhookCreate,
    WebhookDeliveryRead,
    WebhookRead,
)
from app.modules.webhooks.service import WebhookService
from app.schemas import success_response

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.get("")
def list_webhooks(
    event_type: Optional[str] = Query(default=None),
    principal: Principal = Depends(require_any_scope("webhooks:read", "projects:read")),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    subs = service.list_subscriptions(principal, event_type=event_type)
    data = [WebhookRead.model_validate(s).model_dump(mode="json") for s in subs]
    return success_response(data=data, message="Webhook subscriptions retrieved successfully")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreate,
    principal: Principal = Depends(require_any_scope("webhooks:manage", "projects:manage")),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    sub = service.create_subscription(payload, principal)
    return success_response(
        data=WebhookRead.model_validate(sub).model_dump(mode="json"),
        message="Webhook subscription created successfully",
    )


@router.delete("/{webhook_id}")
def disable_webhook(
    webhook_id: uuid.UUID,
    principal: Principal = Depends(require_any_scope("webhooks:manage", "projects:manage")),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    disabled = service.disable_subscription(webhook_id, principal)
    return success_response(
        data=WebhookRead.model_validate(disabled).model_dump(mode="json"),
        message="Webhook subscription disabled successfully",
    )


@router.get("/{webhook_id}/deliveries")
def list_webhook_deliveries(
    webhook_id: uuid.UUID,
    principal: Principal = Depends(require_any_scope("webhooks:read", "projects:read")),
    db: Session = Depends(get_db),
):
    service = WebhookService(db)
    deliveries = service.list_deliveries(webhook_id, principal)
    data = [WebhookDeliveryRead.model_validate(d).model_dump(mode="json") for d in deliveries]
    return success_response(data=data, message="Webhook deliveries retrieved successfully")

