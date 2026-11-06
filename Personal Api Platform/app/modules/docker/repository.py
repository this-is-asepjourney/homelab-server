"""Repository placeholder for docker module."""

from sqlalchemy.orm import Session


class DockerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

