import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from apps.api.app.models.entities import Job, Deployment
from apps.api.app.websocket.manager import ws_manager
from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)

async def create_and_dispatch_job(
    db: Session,
    server_id: str,
    job_type: str,
    payload: Dict[str, Any],
    deployment_id: Optional[str] = None,
    priority: int = 10
) -> Job:
    job = Job(
        server_id=server_id,
        deployment_id=deployment_id,
        job_type=job_type,
        payload=payload,
        status="queued",
        priority=priority,
        attempts=0
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Attempt to dispatch immediately via WebSocket to active agent
    notification = {
        "event": "job.dispatch",
        "job_id": job.id,
        "job_type": job.job_type,
        "server_id": server_id,
        "payload": job.payload
    }
    sent = await ws_manager.send_to_agent(server_id, notification)
    if sent:
        job.status = "running"
        job.locked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        
    return job

def claim_next_job(db: Session, server_id: str) -> Optional[Job]:
    """Claim pending job from queue with row locking."""
    query = db.query(Job).filter(
        Job.server_id == server_id,
        Job.status == "queued"
    ).order_by(Job.priority.desc(), Job.created_at.asc())

    # Skip locked for PostgreSQL
    if not settings.DATABASE_URL.startswith("sqlite"):
        query = query.with_for_update(skip_locked=True)

    job = query.first()
    if job:
        job.status = "running"
        job.attempts += 1
        job.locked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
    return job

def complete_job(
    db: Session,
    job_id: str,
    status: str,
    output: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    duration_seconds: int = 0
) -> Optional[Job]:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None

    job.status = "success" if status == "success" else "failed"
    job.finished_at = datetime.now(timezone.utc)

    # If linked to a deployment, update deployment status
    if job.deployment_id:
        deployment = db.query(Deployment).filter(Deployment.id == job.deployment_id).first()
        if deployment:
            deployment.status = "success" if status == "success" else "failed"
            deployment.finished_at = datetime.now(timezone.utc)
            deployment.duration_seconds = duration_seconds
            
            # If deployment succeeded and an image tag was created, update project status
            if status == "success" and job.payload.get("image_tag"):
                deployment.image_tag = job.payload.get("image_tag")
                if deployment.project:
                    deployment.project.status = "active"

    db.commit()
    db.refresh(job)
    return job

