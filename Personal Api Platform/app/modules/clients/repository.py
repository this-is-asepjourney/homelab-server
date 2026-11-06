"""Repository for API clients and hashed API keys."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.clients.models import ApiClient, ApiKey


class ClientRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, id_val: uuid.UUID) -> Optional[ApiClient]:
        return self.db.get(ApiClient, id_val)

    def get_by_client_id(self, client_id_str: str) -> Optional[ApiClient]:
        return self.db.scalar(select(ApiClient).where(ApiClient.client_id == client_id_str.strip()))

    def list_clients(
        self,
        project_id: Optional[uuid.UUID] = None,
        allowed_project_ids: Optional[set[uuid.UUID]] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApiClient], int]:
        stmt = select(ApiClient)
        count_stmt = select(func.count()).select_from(ApiClient)

        if project_id:
            stmt = stmt.where(ApiClient.project_id == project_id)
            count_stmt = count_stmt.where(ApiClient.project_id == project_id)
        elif allowed_project_ids is not None:
            if not allowed_project_ids:
                return [], 0
            stmt = stmt.where(ApiClient.project_id.in_(allowed_project_ids))
            count_stmt = count_stmt.where(ApiClient.project_id.in_(allowed_project_ids))

        stmt = stmt.order_by(ApiClient.created_at.desc()).offset(offset).limit(limit)
        items = list(self.db.scalars(stmt).all())
        total = int(self.db.scalar(count_stmt) or 0)
        return items, total

    def create_client(self, client: ApiClient) -> ApiClient:
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        return client

    def save_client(self, client: ApiClient) -> ApiClient:
        self.db.commit()
        self.db.refresh(client)
        return client

    def create_api_key(self, api_key: ApiKey) -> ApiKey:
        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)
        return api_key

    def get_api_key(self, key_id: uuid.UUID) -> Optional[ApiKey]:
        return self.db.get(ApiKey, key_id)

    def revoke_api_key(self, api_key: ApiKey) -> ApiKey:
        api_key.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(api_key)
        return api_key

