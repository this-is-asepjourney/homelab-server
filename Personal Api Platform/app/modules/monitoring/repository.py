"""Repository for monitoring platform entity counts."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.clients.models import ApiClient
from app.modules.iot.models import Device
from app.modules.projects.models import Project
from app.modules.webhooks.models import WebhookSubscription


class MonitoringRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def count_projects(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Project)) or 0)

    def count_active_clients(self) -> int:
        stmt = select(func.count()).select_from(ApiClient).where(ApiClient.is_active.is_(True))
        return int(self.db.scalar(stmt) or 0)

    def count_devices(self) -> tuple[int, int]:
        total = int(self.db.scalar(select(func.count()).select_from(Device)) or 0)
        online = int(
            self.db.scalar(
                select(func.count()).select_from(Device).where(Device.status == "online")
            )
            or 0
        )
        return total, online

    def count_active_webhooks(self) -> int:
        stmt = (
            select(func.count())
            .select_from(WebhookSubscription)
            .where(WebhookSubscription.is_active.is_(True))
        )
        return int(self.db.scalar(stmt) or 0)

