"""Repository for webhook subscriptions and delivery tracking."""

from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.webhooks.models import WebhookDelivery, WebhookSubscription


class WebhookRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, subscription_id: uuid.UUID) -> Optional[WebhookSubscription]:
        return self.db.get(WebhookSubscription, subscription_id)

    def list_subscriptions(
        self,
        allowed_project_ids: Optional[set[uuid.UUID]] = None,
        event_type: Optional[str] = None,
    ) -> list[WebhookSubscription]:
        stmt = select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
        if allowed_project_ids is not None:
            if not allowed_project_ids:
                return []
            stmt = stmt.where(WebhookSubscription.project_id.in_(allowed_project_ids))
        if event_type:
            stmt = stmt.where(WebhookSubscription.event_type == event_type)
        return list(self.db.scalars(stmt).all())

    def list_active_by_event_type(self, event_type: str) -> list[WebhookSubscription]:
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.event_type == event_type,
            WebhookSubscription.is_active.is_(True),
        )
        return list(self.db.scalars(stmt).all())

    def create(self, sub: WebhookSubscription) -> WebhookSubscription:
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def disable(self, sub: WebhookSubscription) -> WebhookSubscription:
        sub.is_active = False
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def get_delivery(
        self, subscription_id: uuid.UUID, event_id: str
    ) -> Optional[WebhookDelivery]:
        stmt = select(WebhookDelivery).where(
            WebhookDelivery.subscription_id == subscription_id,
            WebhookDelivery.event_id == event_id,
        )
        return self.db.scalar(stmt)

    def create_delivery(self, delivery: WebhookDelivery) -> WebhookDelivery:
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def list_deliveries(self, subscription_id: uuid.UUID) -> list[WebhookDelivery]:
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.subscription_id == subscription_id)
            .order_by(WebhookDelivery.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

