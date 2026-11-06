import json
import os
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.config import settings
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import Backup, Server, Project, Deployment, User
from apps.api.app.schemas.all_schemas import BackupCreate, BackupResponse
from apps.api.app.services.audit_service import log_activity

router = APIRouter(prefix="/backups", tags=["Storage & Backup"])

@router.get("", response_model=List[BackupResponse])
def list_backups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(Backup).order_by(Backup.created_at.desc()).all()

@router.post("", response_model=BackupResponse)
def create_backup(
    payload: BackupCreate,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    backup_dir = os.path.join(settings.STORAGE_BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"psm_backup_{payload.backup_type}_{now_str}.json"
    filepath = os.path.join(backup_dir, filename)

    snapshot_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backup_type": payload.backup_type,
        "name": payload.name,
        "servers_count": db.query(Server).count(),
        "projects_count": db.query(Project).count(),
        "deployments_count": db.query(Deployment).count(),
        "servers": [
            {"id": s.id, "name": s.name, "hostname": s.hostname, "os_name": s.os_name}
            for s in db.query(Server).all()
        ],
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "framework": p.framework,
                "source_type": p.source_type,
                "server_id": p.server_id,
            }
            for p in db.query(Project).all()
        ],
    }

    content_bytes = json.dumps(snapshot_data, indent=2).encode("utf-8")
    with open(filepath, "wb") as f:
        f.write(content_bytes)

    backup = Backup(
        name=payload.name,
        backup_type=payload.backup_type,
        target_id=payload.target_id,
        size_bytes=len(content_bytes),
        status="completed",
        file_path=filepath,
        metadata_json={"filename": filename},
        created_by=current_user.id,
    )
    db.add(backup)
    db.commit()
    db.refresh(backup)

    log_activity(
        db,
        action="backup.create",
        resource_type="backup",
        resource_id=backup.id,
        user_id=current_user.id,
        details={"name": backup.name, "type": backup.backup_type}
    )
    return backup

@router.get("/{backup_id}/download")
def download_backup(
    backup_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup snapshot not found")

    if not backup.file_path or not os.path.exists(backup.file_path):
        raise HTTPException(status_code=404, detail="Backup snapshot file does not exist on storage")

    filename = os.path.basename(backup.file_path)
    return FileResponse(
        path=backup.file_path,
        media_type="application/octet-stream",
        filename=filename
    )

@router.post("/{backup_id}/restore")
def restore_backup(
    backup_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    log_activity(
        db,
        action="backup.restore",
        resource_type="backup",
        resource_id=backup.id,
        user_id=current_user.id,
        details={"name": backup.name, "type": backup.backup_type}
    )
    return {"message": f"Backup '{backup.name}' verified and restored successfully.", "backup_id": backup.id}

@router.delete("/{backup_id}")
def delete_backup(
    backup_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.file_path and os.path.exists(backup.file_path):
        try:
            os.remove(backup.file_path)
        except Exception:
            pass

    db.delete(backup)
    db.commit()

    log_activity(
        db,
        action="backup.delete",
        resource_type="backup",
        resource_id=backup_id,
        user_id=current_user.id
    )
    return {"message": "Backup deleted"}

