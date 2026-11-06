"""Repository for append-oriented audit log records."""

from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

    def list_logs(
        self,
        project_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        client_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        if project_id:
            stmt = stmt.where(AuditLog.project_id == project_id)
            count_stmt = count_stmt.where(AuditLog.project_id == project_id)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
            count_stmt = count_stmt.where(AuditLog.user_id == user_id)
        if client_id:
            stmt = stmt.where(AuditLog.client_id == client_id)
            count_stmt = count_stmt.where(AuditLog.client_id == client_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)

        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        items = list(self.db.scalars(stmt).all())
        total = int(self.db.scalar(count_stmt) or 0)
        return items, total

