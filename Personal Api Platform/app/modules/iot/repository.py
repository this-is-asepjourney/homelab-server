"""Repository for IoT devices, credentials, telemetry, and commands."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.iot.models import Device, DeviceCredential, IotCommand, IotTelemetry


class IotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, device_id: uuid.UUID) -> Optional[Device]:
        return self.db.get(Device, device_id)

    def get_by_uid(self, device_uid: str) -> Optional[Device]:
        return self.db.scalar(select(Device).where(Device.device_uid == device_uid.strip()))

    def list_devices(
        self, allowed_project_ids: Optional[set[uuid.UUID]] = None
    ) -> list[Device]:
        stmt = select(Device).order_by(Device.created_at.desc())
        if allowed_project_ids is not None:
            if not allowed_project_ids:
                return []
            stmt = stmt.where(Device.project_id.in_(allowed_project_ids))
        return list(self.db.scalars(stmt).all())

    def create_device(self, device: Device) -> Device:
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        return device

    def save_device(self, device: Device) -> Device:
        self.db.commit()
        self.db.refresh(device)
        return device

    def delete_device(self, device: Device) -> None:
        self.db.delete(device)
        self.db.commit()

    def create_credential(self, cred: DeviceCredential) -> DeviceCredential:
        self.db.add(cred)
        self.db.commit()
        self.db.refresh(cred)
        return cred

    def revoke_active_credentials(self, device_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        stmt = select(DeviceCredential).where(
            DeviceCredential.device_id == device_id,
            DeviceCredential.revoked_at.is_(None),
        )
        creds = list(self.db.scalars(stmt).all())
        for c in creds:
            c.revoked_at = now
        self.db.commit()
        return len(creds)

    def create_telemetry(self, telemetry: IotTelemetry) -> IotTelemetry:
        self.db.add(telemetry)
        self.db.commit()
        self.db.refresh(telemetry)
        return telemetry

    def list_telemetry(
        self, device_id: uuid.UUID, limit: int = 50
    ) -> list[IotTelemetry]:
        stmt = (
            select(IotTelemetry)
            .where(IotTelemetry.device_id == device_id)
            .order_by(IotTelemetry.timestamp.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def create_command(self, cmd: IotCommand) -> IotCommand:
        self.db.add(cmd)
        self.db.commit()
        self.db.refresh(cmd)
        return cmd

    def get_command_by_correlation(self, correlation_id: str) -> Optional[IotCommand]:
        return self.db.scalar(
            select(IotCommand).where(IotCommand.correlation_id == correlation_id)
        )

