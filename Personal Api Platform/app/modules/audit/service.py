"""Service for recording and querying platform audit events."""

from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_request_id, redact_value
from app.core.permissions import Principal
from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditRepository(db)

    def record(
        self,
        action: str,
        resource: str,
        principal: Optional[Principal] = None,
        project_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        client_id: Optional[uuid.UUID] = None,
        resource_id: Optional[str] = None,
        status: str = "success",
        ip_address: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        resolved_user_id = user_id or (principal.user_id if principal else None)
        resolved_client_id = client_id or (principal.client_id if principal else None)
        resolved_project_id = project_id or (principal.project_id if principal else None)

        safe_details = redact_value(details) if details else None

        log_entry = AuditLog(
            project_id=resolved_project_id,
            user_id=resolved_user_id,
            client_id=resolved_client_id,
            action=action,
            resource=resource,
            resource_id=str(resource_id) if resource_id else None,
            status=status,
            ip_address=ip_address,
            request_id=get_request_id(),
            details=safe_details,
        )
        return self.repo.create(log_entry)

    def list_audit_logs(
        self,
        principal: Principal,
        project_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        client_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        if project_id and not principal.is_admin:
            principal.require_project_access(project_id)
        elif not principal.is_admin and principal.project_id:
            project_id = principal.project_id

        offset = (page - 1) * page_size
        return self.repo.list_logs(
            project_id=project_id,
            user_id=user_id,
            client_id=client_id,
            action=action,
            offset=offset,
            limit=page_size,
        )

