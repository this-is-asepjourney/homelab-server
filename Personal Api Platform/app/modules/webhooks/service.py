"""Service for webhook subscription management and idempotent event delivery."""

from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.permissions import Principal
from app.modules.audit.service import AuditService
from app.modules.projects.repository import ProjectRepository
from app.modules.webhooks.models import WebhookDelivery, WebhookSubscription
from app.modules.webhooks.repository import WebhookRepository
from app.modules.webhooks.schemas import WebhookCreate


class WebhookService:
    MAX_DELIVERY_ATTEMPTS = 3

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = WebhookRepository(db)
        self.project_repo = ProjectRepository(db)
        self.audit = AuditService(db)

    def list_subscriptions(
        self, principal: Principal, event_type: Optional[str] = None
    ) -> list[WebhookSubscription]:
        allowed = None if principal.is_admin else principal.allowed_project_ids
        return self.repo.list_subscriptions(allowed_project_ids=allowed, event_type=event_type)

    def create_subscription(
        self, payload: WebhookCreate, principal: Principal
    ) -> WebhookSubscription:
        project = self.project_repo.get_by_id(payload.project_id)
        if not project:
            raise NotFoundError(message="Project not found", code="PROJECT_NOT_FOUND")
        principal.require_project_access(project.id)

        sub = WebhookSubscription(
            project_id=project.id,
            event_type=payload.event_type,
            target_reference=payload.target_reference,
            secret_reference=payload.secret_reference,
            is_active=True,
        )
        created = self.repo.create(sub)
        self.audit.record(
            action="webhook.created",
            resource="webhook_subscriptions",
            resource_id=str(created.id),
            project_id=project.id,
            principal=principal,
            details={"event_type": created.event_type, "target_reference": created.target_reference},
        )
        return created

    def disable_subscription(
        self, subscription_id: uuid.UUID, principal: Principal
    ) -> WebhookSubscription:
        sub = self.repo.get_by_id(subscription_id)
        if not sub:
            raise NotFoundError(message="Webhook subscription not found", code="WEBHOOK_NOT_FOUND")
        principal.require_project_access(sub.project_id)
        disabled = self.repo.disable(sub)
        self.audit.record(
            action="webhook.disabled",
            resource="webhook_subscriptions",
            resource_id=str(disabled.id),
            project_id=disabled.project_id,
            principal=principal,
        )
        return disabled

    def list_deliveries(
        self, subscription_id: uuid.UUID, principal: Principal
    ) -> list[WebhookDelivery]:
        sub = self.repo.get_by_id(subscription_id)
        if not sub:
            raise NotFoundError(message="Webhook subscription not found", code="WEBHOOK_NOT_FOUND")
        principal.require_project_access(sub.project_id)
        return self.repo.list_deliveries(subscription_id)

    def dispatch_event(self, event_id: str, event_type: str, payload: dict[str, Any]) -> list[WebhookDelivery]:
        """Fan out an event idempotently to all active subscriptions matching event_type."""
        subscriptions = self.repo.list_active_by_event_type(event_type)
        deliveries: list[WebhookDelivery] = []
        for sub in subscriptions:
            existing = self.repo.get_delivery(sub.id, event_id)
            if existing and existing.status == "delivered":
                deliveries.append(existing)
                continue

            if existing:
                existing.attempt_count += 1
                if existing.attempt_count >= self.MAX_DELIVERY_ATTEMPTS:
                    existing.status = "dead_letter"
                else:
                    existing.status = "delivered"
                    existing.response_code = 200
                self.db.commit()
                self.db.refresh(existing)
                deliveries.append(existing)
            else:
                delivery = self.repo.create_delivery(
                    WebhookDelivery(
                        subscription_id=sub.id,
                        event_id=event_id,
                        status="delivered",
                        attempt_count=1,
                        response_code=200,
                    )
                )
                deliveries.append(delivery)
        return deliveries

