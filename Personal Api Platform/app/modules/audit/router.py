"""HTTP router for audit log inspection."""

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_scopes
from app.modules.audit.schemas import AuditLogRead
from app.modules.audit.service import AuditService
from app.schemas import success_response

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("")
def list_audit_logs(
    project_id: Optional[uuid.UUID] = Query(default=None),
    user_id: Optional[uuid.UUID] = Query(default=None),
    client_id: Optional[uuid.UUID] = Query(default=None),
    action: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_scopes("audit:read")),
    db: Session = Depends(get_db),
):
    service = AuditService(db)
    items, total = service.list_audit_logs(
        principal=principal,
        project_id=project_id,
        user_id=user_id,
        client_id=client_id,
        action=action,
        page=page,
        page_size=page_size,
    )
    serialized = [AuditLogRead.model_validate(item).model_dump(mode="json") for item in items]
    return success_response(
        data=serialized,
        message="Audit logs retrieved successfully",
        page=page,
        page_size=page_size,
        total=total,
    )

