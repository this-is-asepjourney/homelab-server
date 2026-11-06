"""Repository for checking database readiness."""

from sqlalchemy import text
from sqlalchemy.orm import Session


class ServerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ping_database(self) -> bool:
        try:
            self.db.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

