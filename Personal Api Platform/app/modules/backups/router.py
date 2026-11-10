"""FastAPI router for Homelab Backup & Disaster Recovery."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.modules.backups.service import BackupService

router = APIRouter(prefix="/backups", tags=["Backups & Disaster Recovery"])


class CreateBackupRequest(BaseModel):
    scope: str = Field(default="all", description="Scope: 'all', 'databases', or 'configs'")
    note: Optional[str] = Field(default="", description="Optional label or note for this backup")


@router.post("/create", status_code=status.HTTP_201_CREATED)
def trigger_backup(payload: Optional[CreateBackupRequest] = None):
    """Triggers an on-demand backup of Homelab databases and configurations."""
    scope = payload.scope if payload else "all"
    note = payload.note if payload else ""
    try:
        manifest = BackupService.create_backup(scope=scope, note=note)
        return {
            "success": True,
            "message": f"Backup created successfully ({manifest['archive']['size_human']})",
            "data": manifest,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {e}",
        )


@router.get("")
def list_backups():
    """Lists all available homelab backup archives with sizes, checksums, and timestamps."""
    backups = BackupService.list_backups()
    total_bytes = sum(b.get("size_bytes", 0) for b in backups)
    return {
        "success": True,
        "count": len(backups),
        "total_storage_bytes": total_bytes,
        "data": backups,
    }


@router.get("/{filename}/download")
def download_backup(filename: str):
    """Downloads the selected .tar.gz backup archive."""
    path = BackupService.get_backup_path(filename)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup archive not found")

    return FileResponse(
        path=path,
        media_type="application/gzip",
        filename=path.name,
    )


@router.get("/{filename}/manifest")
def view_backup_manifest(filename: str):
    """Returns the JSON manifest detailing files, database row counts, and checksums in the archive."""
    manifest = BackupService.get_backup_manifest(filename)
    if not manifest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup or manifest not found")
    return {"success": True, "data": manifest}


@router.post("/{filename}/verify")
@router.get("/{filename}/verify")
def verify_backup_integrity(filename: str):
    """Verifies the integrity of a backup archive, validates tar structure, checksums, and parses SQL/Flux headers."""
    report = BackupService.verify_backup(filename)
    if not report.get("exists"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup archive not found")
    return {
        "success": True,
        "message": f"Verification completed: {report.get('status')} ({report.get('integrity_score_percent', 0)}%)",
        "data": report,
    }


@router.delete("/{filename}")
def delete_backup(filename: str):
    """Permanently deletes a backup archive and its metadata."""
    success = BackupService.delete_backup(filename)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup archive not found or deletion failed")
    return {"success": True, "message": f"Backup {filename} deleted successfully"}

