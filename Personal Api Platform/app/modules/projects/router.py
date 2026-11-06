"""HTTP router for project registration and management."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_scopes
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectMembershipCreate,
    ProjectMembershipRead,
    ProjectRead,
    ProjectUpdate,
)
from app.modules.projects.service import ProjectService
from app.schemas import success_response

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("")
def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_scopes("projects:read")),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    projects, total = service.list_projects(principal, page=page, page_size=page_size)
    data = [ProjectRead.model_validate(p).model_dump(mode="json") for p in projects]
    return success_response(
        data=data,
        message="Projects retrieved successfully",
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    principal: Principal = Depends(require_scopes("projects:manage")),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    project = service.create_project(payload, principal)
    return success_response(
        data=ProjectRead.model_validate(project).model_dump(mode="json"),
        message="Project registered successfully",
    )


@router.get("/{project_id}")
def get_project(
    project_id: str,
    principal: Principal = Depends(require_scopes("projects:read")),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    project = service.get_project(project_id, principal)
    return success_response(
        data=ProjectRead.model_validate(project).model_dump(mode="json"),
        message="Project details retrieved successfully",
    )


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    principal: Principal = Depends(require_scopes("projects:manage")),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    project = service.update_project(project_id, payload, principal)
    return success_response(
        data=ProjectRead.model_validate(project).model_dump(mode="json"),
        message="Project updated successfully",
    )


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: str,
    payload: ProjectMembershipCreate,
    principal: Principal = Depends(require_scopes("projects:manage")),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    membership = service.add_member(project_id, payload, principal)
    return success_response(
        data=ProjectMembershipRead.model_validate(membership).model_dump(mode="json"),
        message="Project member added successfully",
    )

