import csv
import io
import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import AuditLog, User
from apps.api.app.schemas.all_schemas import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

@router.get("/export")
def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    """Export complete audit trail as CSV or JSON for compliance and offline analysis."""
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).all()
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        data = [
            {
                "id": l.id,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "user_name": l.user.name if l.user else "System",
                "ip_address": l.ip_address,
                "details": l.details,
                "created_at": l.created_at.isoformat() if l.created_at else ""
            }
            for l in logs
        ]
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="psm_audit_logs_{now_str}.json"'}
        )

    # CSV Format
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp (UTC)", "Actor", "Action", "Resource Type", "Resource ID", "IP Address", "Details"])
    for l in logs:
        writer.writerow([
            l.id,
            l.created_at.isoformat() if l.created_at else "",
            l.user.name if l.user else "System",
            l.action,
            l.resource_type,
            l.resource_id or "",
            l.ip_address or "",
            json.dumps(l.details) if l.details else ""
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="psm_audit_logs_{now_str}.csv"'}
    )

@router.get("", response_model=List[AuditLogResponse])
def get_audit_logs(
    limit: int = Query(50, le=200),
    offset: int = 0,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    results = []
    for log in logs:
        results.append(
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                user_name=log.user.name if log.user else "System",
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                details=log.details,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
        )
    return results

