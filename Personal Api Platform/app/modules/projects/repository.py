"""Repository for registered projects and user memberships."""

from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.projects.models import Project, UserProjectMembership


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, project_id: uuid.UUID) -> Optional[Project]:
        return self.db.get(Project, project_id)

    def get_by_slug(self, slug: str) -> Optional[Project]:
        return self.db.scalar(select(Project).where(Project.slug == slug.strip().lower()))

    def list_projects(
        self,
        allowed_ids: Optional[set[uuid.UUID]] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Project], int]:
        stmt = select(Project)
        count_stmt = select(func.count()).select_from(Project)
        if allowed_ids is not None:
            if not allowed_ids:
                return [], 0
            stmt = stmt.where(Project.id.in_(allowed_ids))
            count_stmt = count_stmt.where(Project.id.in_(allowed_ids))

        stmt = stmt.order_by(Project.created_at.desc()).offset(offset).limit(limit)
        items = list(self.db.scalars(stmt).all())
        total = int(self.db.scalar(count_stmt) or 0)
        return items, total

    def create(self, project: Project) -> Project:
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def save(self, project: Project) -> Project:
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_membership(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> Optional[UserProjectMembership]:
        stmt = select(UserProjectMembership).where(
            UserProjectMembership.user_id == user_id,
            UserProjectMembership.project_id == project_id,
        )
        return self.db.scalar(stmt)

    def add_membership(self, membership: UserProjectMembership) -> UserProjectMembership:
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

