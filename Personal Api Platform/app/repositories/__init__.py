"""Shared repository base classes and helpers."""

from typing import Generic, Optional, TypeVar
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic SQLAlchemy repository supporting common CRUD operations."""

    def __init__(self, db: Session, model: type[ModelType]) -> None:
        self.db = db
        self.model = model

    def get_by_id(self, entity_id: uuid.UUID) -> Optional[ModelType]:
        return self.db.get(self.model, entity_id)

    def list_all(self, offset: int = 0, limit: int = 50) -> list[ModelType]:
        stmt = select(self.model).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

