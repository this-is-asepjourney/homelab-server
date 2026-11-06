"""Repository for PAP user persistence."""

from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.users.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.scalar(select(User).where(User.email == email.strip().lower()))

    def list_users(self, offset: int = 0, limit: int = 50) -> tuple[list[User], int]:
        stmt = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        total = int(self.db.scalar(select(func.count()).select_from(User)) or 0)
        return list(self.db.scalars(stmt).all()), total

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user

