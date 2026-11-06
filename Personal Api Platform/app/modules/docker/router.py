"""HTTP router for Docker container inspection and restricted restart operations."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_scopes
from app.modules.docker.service import DockerService
from app.schemas import success_response

router = APIRouter(prefix="/docker", tags=["Docker"])


@router.get("/containers")
def list_containers(
    principal: Principal = Depends(require_scopes("docker:read")),
    db: Session = Depends(get_db),
):
    service = DockerService(db)
    return success_response(
        data=service.list_containers(),
        message="Docker containers retrieved successfully",
    )


@router.get("/containers/{container_id}")
def get_container_details(
    container_id: str,
    principal: Principal = Depends(require_scopes("docker:read")),
    db: Session = Depends(get_db),
):
    service = DockerService(db)
    return success_response(
        data=service.get_container(container_id),
        message="Container details retrieved successfully",
    )


@router.get("/containers/{container_id}/stats")
def get_container_stats(
    container_id: str,
    principal: Principal = Depends(require_scopes("docker:read")),
    db: Session = Depends(get_db),
):
    service = DockerService(db)
    return success_response(
        data=service.get_container_stats(container_id),
        message="Container resource usage retrieved successfully",
    )


@router.post("/containers/{container_id}/restart")
def restart_container(
    container_id: str,
    principal: Principal = Depends(require_scopes("docker:restart")),
    db: Session = Depends(get_db),
):
    service = DockerService(db)
    return success_response(
        data=service.restart_container(container_id, principal),
        message="Container restart executed successfully",
    )

