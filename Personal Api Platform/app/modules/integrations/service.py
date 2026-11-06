"""Service for business integration registry and Stock UMKM / POS Cashier / PSM / IoT adapter operations."""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.integrations.mqtt import MqttAdapter
from app.integrations.prometheus import PrometheusAdapter
from app.integrations.psm import PsmAdapter
from app.integrations.stock_umkm import StockUmkmAdapter
from app.modules.audit.service import AuditService
from app.modules.clients.repository import ClientRepository
from app.modules.integrations.models import Integration, IntegrationEvent
from app.modules.integrations.repository import IntegrationRepository
from app.modules.integrations.schemas import (
    IntegrationCreate,
    PsmSyncPayload,
    StockUmkmEventInput,
)
from app.modules.iot.fleet_router import FleetService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.webhooks.service import WebhookService
from app.services.bootstrap import seed_platform_registry


class IntegrationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = IntegrationRepository(db)
        self.project_repo = ProjectRepository(db)
        self.client_repo = ClientRepository(db)
        self.webhook_service = WebhookService(db)
        self.audit = AuditService(db)
        self.stock_adapter = StockUmkmAdapter()
        self.psm_adapter = PsmAdapter()

    def list_integrations(self, principal: Principal) -> list[Integration]:
        allowed = None if principal.is_admin else principal.allowed_project_ids
        return self.repo.list_integrations(allowed_project_ids=allowed)

    def create_integration(
        self, payload: IntegrationCreate, principal: Principal
    ) -> Integration:
        project = self.project_repo.get_by_id(payload.project_id)
        if not project:
            raise NotFoundError(message="Project not found", code="PROJECT_NOT_FOUND")
        principal.require_project_access(project.id)

        if self.repo.get_by_name(payload.name):
            raise ConflictError(
                message=f"Integration '{payload.name}' already exists",
                code="INTEGRATION_EXISTS",
            )

        integration = Integration(
            project_id=project.id,
            name=payload.name,
            integration_type=payload.integration_type,
            configuration=payload.configuration,
            secret_reference=payload.secret_reference,
            is_active=True,
        )
        created = self.repo.create(integration)
        self.audit.record(
            action="integration.created",
            resource="integrations",
            resource_id=str(created.id),
            project_id=project.id,
            principal=principal,
            details={"name": created.name, "type": created.integration_type},
        )
        return created

    def check_integration_health(
        self, integration_id: uuid.UUID, principal: Principal
    ) -> dict[str, Any]:
        integration = self.repo.get_by_id(integration_id)
        if not integration:
            raise NotFoundError(message="Integration not found", code="INTEGRATION_NOT_FOUND")
        principal.require_project_access(integration.project_id)

        if integration.integration_type == "prometheus":
            status_info = PrometheusAdapter().check_health()
        elif integration.integration_type == "mqtt":
            status_info = MqttAdapter().check_health()
        elif integration.integration_type == "psm_api":
            status_info = self.psm_adapter.check_health()
        else:
            status_info = self.stock_adapter.check_health()

        return {
            "integration_id": str(integration.id),
            "name": integration.name,
            "integration_type": integration.integration_type,
            "is_active": integration.is_active,
            "upstream": status_info,
        }

    def get_stock_umkm_products(
        self,
        search: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self.stock_adapter.list_products(search=search, product_id=product_id)

    def get_stock_umkm_inventory(
        self, product_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        items = self.stock_adapter.list_inventory(product_id=product_id)
        by_product = {item["product_id"]: item for item in items}

        # Apply committed inventory.updated events idempotently
        events = self.repo.list_events_by_type("inventory.updated")
        for ev in events:
            pid = str(ev.data.get("product_id", ""))
            qty = ev.data.get("quantity")
            if pid and isinstance(qty, (int, float)):
                if pid in by_product:
                    by_product[pid]["quantity"] = int(qty)
                    by_product[pid]["available"] = max(
                        0, int(qty) - int(by_product[pid].get("reserved", 0))
                    )
                elif not product_id or product_id == pid:
                    by_product[pid] = {
                        "product_id": pid,
                        "sku": f"UMKM-PROD-{pid}",
                        "warehouse": "main",
                        "quantity": int(qty),
                        "reserved": 0,
                        "available": int(qty),
                    }

        return list(by_product.values())

    def ingest_stock_umkm_event(
        self, payload: StockUmkmEventInput, principal: Principal
    ) -> dict[str, Any]:
        existing = self.repo.get_event_by_event_id(payload.event_id)
        if existing:
            return {
                "id": str(existing.id),
                "event_id": existing.event_id,
                "event_type": existing.event_type,
                "source": existing.source,
                "status": existing.status,
                "idempotent_replay": True,
                "webhook_deliveries": 0,
            }

        event_record = self.repo.create_event(
            IntegrationEvent(
                event_id=payload.event_id,
                event_type=payload.event_type,
                source=payload.source,
                occurred_at=payload.occurred_at,
                data=payload.data,
                status="processed",
            )
        )
        deliveries = self.webhook_service.dispatch_event(
            event_id=payload.event_id,
            event_type=payload.event_type,
            payload=payload.model_dump(mode="json"),
        )
        self.audit.record(
            action="integration.event_received",
            resource="integration_events",
            resource_id=str(event_record.id),
            principal=principal,
            details={
                "event_id": payload.event_id,
                "event_type": payload.event_type,
                "source": payload.source,
                "webhook_deliveries": len(deliveries),
            },
        )
        return {
            "id": str(event_record.id),
            "event_id": event_record.event_id,
            "event_type": event_record.event_type,
            "source": event_record.source,
            "status": event_record.status,
            "idempotent_replay": False,
            "webhook_deliveries": len(deliveries),
        }

    def sync_psm_state(
        self, payload: PsmSyncPayload, principal: Principal
    ) -> dict[str, Any]:
        seed_platform_registry(self.db)
        psm_project = self.project_repo.get_by_slug("personal-server-manager")
        if not psm_project:
            psm_project = self.project_repo.create(
                Project(
                    slug="personal-server-manager",
                    name="Personal Server Manager",
                    description="Multi-server control plane, Docker container manager, and deployment orchestrator",
                    status="active",
                )
            )

        # Register any custom projects pushed from PSM into PAP's project registry
        synced_projects: list[str] = []
        for proj in payload.projects:
            name = str(proj.get("name") or "").strip()
            if not name:
                continue
            slug = name.lower().replace(" ", "-").replace("_", "-")
            existing_proj = self.project_repo.get_by_slug(slug)
            if not existing_proj:
                self.project_repo.create(
                    Project(
                        slug=slug,
                        name=name,
                        description=proj.get("description") or f"Managed by PSM ({proj.get('framework', 'App')})",
                        status=proj.get("status", "active"),
                    )
                )
            synced_projects.append(slug)

        integration = self.repo.get_by_name("psm-control-plane-api")
        now_iso = datetime.now(timezone.utc).isoformat()
        servers = payload.servers or self.psm_adapter.DEFAULT_SERVERS_SNAPSHOT
        containers = payload.containers or self.psm_adapter.DEFAULT_CONTAINERS_SNAPSHOT

        config_data = {
            "base_url": get_settings().PSM_API_URL,
            "web_url": "http://192.168.25.101:3005",
            "last_synced_at": now_iso,
            "synced_servers": len(servers),
            "synced_containers": len(containers),
            "synced_projects": synced_projects,
            "servers": servers,
            "containers": containers,
            "resources": payload.resources,
        }

        if integration:
            integration.configuration = config_data
            self.db.commit()
            self.db.refresh(integration)
        else:
            integration = self.repo.create(
                Integration(
                    project_id=psm_project.id,
                    name="psm-control-plane-api",
                    integration_type="psm_api",
                    configuration=config_data,
                    secret_reference="PAP_PSM_SERVICE_KEY",
                    is_active=True,
                )
            )

        self.audit.record(
            action="psm.control_plane_synced",
            resource="integrations",
            resource_id=str(integration.id),
            project_id=psm_project.id,
            principal=principal,
            details={
                "servers_count": len(servers),
                "containers_count": len(containers),
                "projects_synced": synced_projects,
            },
        )
        return {
            "status": "synced",
            "synced_at": now_iso,
            "psm_project_id": str(psm_project.id),
            "servers_count": len(servers),
            "containers_count": len(containers),
            "projects_synced": synced_projects,
            "configuration": config_data,
        }

    def get_psm_state(self) -> dict[str, Any]:
        seed_platform_registry(self.db)
        integration = self.repo.get_by_name("psm-control-plane-api")
        cfg = (integration.configuration if integration else {}) or {}
        servers = cfg.get("servers") or self.psm_adapter.DEFAULT_SERVERS_SNAPSHOT
        containers = cfg.get("containers") or self.psm_adapter.DEFAULT_CONTAINERS_SNAPSHOT
        health = self.psm_adapter.check_health()
        return {
            "project_slug": "personal-server-manager",
            "client_id": "psm-control-plane",
            "health": health,
            "last_synced_at": cfg.get("last_synced_at"),
            "servers": servers,
            "containers": containers,
            "resources": cfg.get("resources") or {
                "avg_cpu_percent": 24.5,
                "avg_memory_percent": 58.2,
                "avg_disk_percent": 42.0,
            },
        }

    def get_hub_overview(self) -> dict[str, Any]:
        seed_platform_registry(self.db)
        settings = get_settings()
        fleet_service = FleetService(self.db)
        iot_stats = fleet_service.get_fleet_stats()
        iot_hierarchy = fleet_service.get_hierarchy()
        psm_state = self.get_psm_state()

        projects, total_projects = self.project_repo.list_projects(limit=50)
        clients, total_clients = self.client_repo.list_clients(limit=50)

        return {
            "main_api": {
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "api_prefix": settings.API_PREFIX,
                "base_url": f"http://{settings.HOST_IP}:{settings.PORT}{settings.API_PREFIX}",
                "status": "healthy",
                "architecture": "Modular Monolith",
                "projects_total": total_projects,
                "clients_total": total_clients,
            },
            "connected_projects": [
                {
                    "id": str(p.id),
                    "slug": p.slug,
                    "name": p.name,
                    "status": p.status,
                    "description": p.description,
                }
                for p in projects
            ],
            "clients": [
                {
                    "id": str(c.id),
                    "client_id": c.client_id,
                    "name": c.name,
                    "project_id": str(c.project_id),
                    "is_active": c.is_active,
                    "scopes": sorted([s.name for s in c.scopes]),
                }
                for c in clients
            ],
            "personal_server_manager": psm_state,
            "iot_dashboard": {
                "project_slug": "iot-dashboard",
                "client_id": "iot-dashboard-backend",
                "stats": iot_stats,
                "summary": iot_hierarchy.get("summary", {}),
                "models": [
                    {
                        "id": m["id"],
                        "name": m["name"],
                        "type": m["type"],
                        "status": m["status"],
                        "device_count": m["device_count"],
                        "online_count": m["online_count"],
                        "offline_count": m["offline_count"],
                    }
                    for m in iot_hierarchy.get("models", [])
                ],
                "devices": fleet_service.list_fleet_devices(limit=100),
            },
            "mqtt_broker": {
                "local_host": settings.MQTT_HOST,
                "tailscale_host": getattr(settings, "MQTT_TAILSCALE_HOST", "100.106.63.90"),
                "port": settings.MQTT_PORT,
                "username": settings.MQTT_USERNAME,
                "status": "configured" if settings.MQTT_ENABLED else "disabled",
                "enabled": settings.MQTT_ENABLED,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

