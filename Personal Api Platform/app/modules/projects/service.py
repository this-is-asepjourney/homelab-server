"""Service for project registration, access enforcement, and membership management."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.modules.audit.service import AuditService
from app.modules.projects.models import Project, UserProjectMembership
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectMembershipCreate,
    ProjectUpdate,
)


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProjectRepository(db)
        self.audit = AuditService(db)

    def resolve_project(self, identifier: str | uuid.UUID) -> Project:
        if isinstance(identifier, uuid.UUID):
            project = self.repo.get_by_id(identifier)
        else:
            try:
                uid = uuid.UUID(str(identifier))
                project = self.repo.get_by_id(uid)
            except ValueError:
                project = self.repo.get_by_slug(str(identifier))
        if not project:
            raise NotFoundError(message="Project not found", code="PROJECT_NOT_FOUND")
        return project

    def list_projects(
        self, principal: Principal, page: int = 1, page_size: int = 50
    ) -> tuple[list[Project], int]:
        offset = (page - 1) * page_size
        allowed_ids = None if principal.is_admin else principal.allowed_project_ids
        return self.repo.list_projects(allowed_ids=allowed_ids, offset=offset, limit=page_size)

    def create_project(self, payload: ProjectCreate, principal: Principal) -> Project:
        if self.repo.get_by_slug(payload.slug):
            raise ConflictError(
                message=f"Project with slug '{payload.slug}' already exists",
                code="PROJECT_SLUG_EXISTS",
            )
        project = Project(
            slug=payload.slug.strip().lower(),
            name=payload.name,
            description=payload.description,
            status=payload.status,
        )
        created = self.repo.create(project)
        if principal.user_id and not self.repo.get_membership(principal.user_id, created.id):
            self.repo.add_membership(
                UserProjectMembership(
                    user_id=principal.user_id,
                    project_id=created.id,
                    membership_role="owner",
                )
            )
        self.audit.record(
            action="project.created",
            resource="projects",
            resource_id=str(created.id),
            project_id=created.id,
            principal=principal,
            details={"slug": created.slug, "name": created.name},
        )
        return created

    def get_project(self, project_identifier: str, principal: Principal) -> Project:
        project = self.resolve_project(project_identifier)
        principal.require_project_access(project.id)
        return project

    def update_project(
        self, project_identifier: str, payload: ProjectUpdate, principal: Principal
    ) -> Project:
        project = self.resolve_project(project_identifier)
        principal.require_project_access(project.id)
        if payload.name is not None:
            project.name = payload.name
        if payload.description is not None:
            project.description = payload.description
        if payload.status is not None:
            project.status = payload.status
        updated = self.repo.save(project)
        self.audit.record(
            action="project.updated",
            resource="projects",
            resource_id=str(updated.id),
            project_id=updated.id,
            principal=principal,
            details={"slug": updated.slug, "status": updated.status},
        )
        return updated

    def add_member(
        self,
        project_identifier: str,
        payload: ProjectMembershipCreate,
        principal: Principal,
    ) -> UserProjectMembership:
        project = self.resolve_project(project_identifier)
        principal.require_project_access(project.id)
        existing = self.repo.get_membership(payload.user_id, project.id)
        if existing:
            raise ConflictError(
                message="User is already a member of this project",
                code="MEMBERSHIP_EXISTS",
            )
        membership = self.repo.add_membership(
            UserProjectMembership(
                user_id=payload.user_id,
                project_id=project.id,
                membership_role=payload.membership_role,
            )
        )
        self.audit.record(
            action="project.member_added",
            resource="project_memberships",
            resource_id=str(membership.id),
            project_id=project.id,
            principal=principal,
            details={
                "member_user_id": str(payload.user_id),
                "role": payload.membership_role,
            },
        )
        return membership

