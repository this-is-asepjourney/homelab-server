"""Repository placeholder for metrics module."""

from sqlalchemy.orm import Session


class MetricsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

