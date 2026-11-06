"""Repository for integration configurations and idempotent event records."""

from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.integrations.models import Integration, IntegrationEvent


class IntegrationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, integration_id: uuid.UUID) -> Optional[Integration]:
        return self.db.get(Integration, integration_id)

    def get_by_name(self, name: str) -> Optional[Integration]:
        return self.db.scalar(select(Integration).where(Integration.name == name))

    def list_integrations(
        self, allowed_project_ids: Optional[set[uuid.UUID]] = None
    ) -> list[Integration]:
        stmt = select(Integration).order_by(Integration.created_at.desc())
        if allowed_project_ids is not None:
            if not allowed_project_ids:
                return []
            stmt = stmt.where(Integration.project_id.in_(allowed_project_ids))
        return list(self.db.scalars(stmt).all())

    def create(self, integration: Integration) -> Integration:
        self.db.add(integration)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def get_event_by_event_id(self, event_id: str) -> Optional[IntegrationEvent]:
        return self.db.scalar(
            select(IntegrationEvent).where(IntegrationEvent.event_id == event_id)
        )

    def create_event(self, event: IntegrationEvent) -> IntegrationEvent:
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events_by_type(self, event_type: str) -> list[IntegrationEvent]:
        stmt = (
            select(IntegrationEvent)
            .where(IntegrationEvent.event_type == event_type)
            .order_by(IntegrationEvent.occurred_at.asc())
        )
        return list(self.db.scalars(stmt).all())

