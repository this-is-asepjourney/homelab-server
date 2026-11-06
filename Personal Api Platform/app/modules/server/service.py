"""Service for liveness, readiness, and platform metadata."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.modules.server.repository import ServerRepository


class ServerService:
    MODULES = [
        "auth",
        "users",
        "projects",
        "clients",
        "permissions",
        "database_registry",
        "integrations",
        "iot",
        "metrics",
        "monitoring",
        "server",
        "docker",
        "webhooks",
        "audit",
    ]

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ServerRepository(db)
        self.settings = get_settings()

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "service": "personal-api-platform",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_readiness(self) -> dict[str, Any]:
        db_ok = self.repo.ping_database()
        if not db_ok:
            raise ServiceUnavailableError(
                message="Core database dependency is not ready",
                code="DATABASE_NOT_READY",
                details={"pap_core_database": "unreachable"},
            )
        return {
            "status": "ready",
            "dependencies": {
                "pap_core_database": "ready",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_system_info(self) -> dict[str, Any]:
        return {
            "name": self.settings.APP_NAME,
            "architecture": "Modular Monolith",
            "environment": self.settings.APP_ENV,
            "version": self.settings.APP_VERSION,
            "api_prefix": self.settings.API_PREFIX,
            "network_scope": "LAN/private network only",
            "host_binding": f"{self.settings.HOST_IP}:{self.settings.PORT}",
            "modules": self.MODULES,
        }

    def get_version(self) -> dict[str, Any]:
        return {
            "api_version": "v1",
            "app_version": self.settings.APP_VERSION,
            "prefix": self.settings.API_PREFIX,
        }

