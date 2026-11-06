"""Service for controlled Docker container queries via an isolated executor (never mounts docker.sock in PAP)."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.core.permissions import Principal
from app.modules.audit.service import AuditService


class DockerService:
    """Enforces Blueprint Section 7.3 & 10.3: Docker management is disabled unless a separately secured executor is enabled."""

    MOCK_CONTAINERS: dict[str, dict[str, Any]] = {
        "pap-api": {
            "id": "pap-api",
            "name": "pap-api",
            "image": "personal-api-platform:1.0.0",
            "state": "running",
            "status": "Up",
            "stats": {
                "cpu_percent": 4.2,
                "memory_usage_mb": 78.5,
                "memory_limit_mb": 256.0,
            },
        },
        "grafana": {
            "id": "grafana",
            "name": "grafana",
            "image": "grafana/grafana:latest",
            "state": "running",
            "status": "Up",
            "stats": {
                "cpu_percent": 2.1,
                "memory_usage_mb": 112.0,
                "memory_limit_mb": 512.0,
            },
        },
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.audit = AuditService(db)

    def _require_executor_enabled(self) -> None:
        if not self.settings.DOCKER_EXECUTOR_ENABLED:
            raise ServiceUnavailableError(
                message="Docker management is disabled in the initial release unless a separately secured executor is enabled.",
                code="DOCKER_EXECUTOR_DISABLED",
            )

    def list_containers(self) -> list[dict[str, Any]]:
        self._require_executor_enabled()
        return [
            {k: v for k, v in item.items() if k != "stats"}
            for item in self.MOCK_CONTAINERS.values()
        ]

    def get_container(self, container_id: str) -> dict[str, Any]:
        self._require_executor_enabled()
        container = self.MOCK_CONTAINERS.get(container_id)
        if not container:
            raise NotFoundError(message="Container not found", code="CONTAINER_NOT_FOUND")
        return {k: v for k, v in container.items() if k != "stats"}

    def get_container_stats(self, container_id: str) -> dict[str, Any]:
        self._require_executor_enabled()
        container = self.MOCK_CONTAINERS.get(container_id)
        if not container:
            raise NotFoundError(message="Container not found", code="CONTAINER_NOT_FOUND")
        return {"id": container_id, **container["stats"]}

    def restart_container(self, container_id: str, principal: Principal) -> dict[str, Any]:
        self._require_executor_enabled()
        container = self.MOCK_CONTAINERS.get(container_id)
        if not container:
            raise NotFoundError(message="Container not found", code="CONTAINER_NOT_FOUND")

        self.audit.record(
            action="docker.container_restarted",
            resource="docker_containers",
            resource_id=container_id,
            principal=principal,
            details={"container_id": container_id},
        )
        return {
            "id": container_id,
            "name": container["name"],
            "action": "restart",
            "status": "restarted",
        }

