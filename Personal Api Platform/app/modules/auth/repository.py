"""Repository for refresh token persistence and revocation."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import RefreshToken


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, session_id: uuid.UUID) -> Optional[RefreshToken]:
        return self.db.get(RefreshToken, session_id)

    def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]:
        return self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    def list_user_sessions(self, user_id: uuid.UUID) -> list[RefreshToken]:
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .order_by(RefreshToken.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def create_refresh_token(self, token_record: RefreshToken) -> RefreshToken:
        self.db.add(token_record)
        self.db.commit()
        self.db.refresh(token_record)
        return token_record

    def revoke_session(self, token_record: RefreshToken) -> RefreshToken:
        token_record.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(token_record)
        return token_record

    def revoke_all_user_sessions(self, user_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        sessions = self.list_user_sessions(user_id)
        count = 0
        for s in sessions:
            if s.revoked_at is None:
                s.revoked_at = now
                count += 1
        self.db.commit()
        return count

