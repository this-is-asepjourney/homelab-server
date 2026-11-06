"""Bootstrap service for seeding canonical PAP scopes, roles, and Phase 3 connected projects."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_device_credential, hash_secret_token
from app.modules.clients.models import ApiClient, ApiKey
from app.modules.clients.repository import ClientRepository
from app.modules.database_registry.models import DatabaseConnection
from app.modules.database_registry.repository import DatabaseRegistryRepository
from app.modules.integrations.models import Integration
from app.modules.integrations.repository import IntegrationRepository
from app.modules.iot.models import Device, DeviceCredential
from app.modules.iot.repository import IotRepository
from app.modules.permissions.repository import PermissionsRepository
from app.modules.permissions.service import PermissionsService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository

CONNECTED_PROJECTS_SEED = [
    {
        "slug": "stock-umkm",
        "name": "Stock UMKM",
        "description": "Laravel product, inventory, and business event backend",
        "client_id": "stock-umkm-service",
        "client_name": "Stock UMKM Laravel Client",
        "client_type": "backend",
        "scopes": [
            "inventory:read",
            "inventory:write",
            "transactions:read",
            "transactions:write",
        ],
    },
    {
        "slug": "pos-cashier",
        "name": "POS Cashier",
        "description": "Next.js POS cashier backend for product lookup and sales integration",
        "client_id": "pos-cashier-backend",
        "client_name": "POS Cashier Backend Client",
        "client_type": "backend",
        "scopes": [
            "inventory:read",
            "inventory:write",
            "transactions:read",
            "transactions:write",
        ],
    },
    {
        "slug": "iot-dashboard",
        "name": "IoT Dashboard",
        "description": "Heatpress IoT Fleet dashboard for ESP32 device registry, status, and telemetry",
        "client_id": "iot-dashboard-backend",
        "client_name": "IoT Dashboard Backend Client",
        "client_type": "backend",
        "scopes": [
            "iot:read",
            "iot:write",
            "iot:manage",
            "metrics:read",
            "server:read",
            "projects:read",
            "integrations:read",
        ],
    },
    {
        "slug": "personal-server-manager",
        "name": "Personal Server Manager",
        "description": "Multi-server control plane, Docker container manager, and deployment orchestrator",
        "client_id": "psm-control-plane",
        "client_name": "PSM Control Plane Client",
        "client_type": "backend",
        "scopes": [
            "projects:read",
            "projects:manage",
            "clients:read",
            "clients:manage",
            "iot:read",
            "iot:write",
            "iot:manage",
            "metrics:read",
            "server:read",
            "docker:read",
            "docker:restart",
            "database:read",
            "database:manage",
            "integrations:read",
            "integrations:manage",
            "webhooks:read",
            "webhooks:manage",
            "audit:read",
        ],
    },
]

HEATPRESS_FLEET_DEVICES_SEED = [
    {
        "device_uid": "80:F3:DA:4B:2A:DC",
        "name": "HPM 55 Press 1",
        "device_type": "ESP32",
        "status": "online",
        "metadata": {
            "mac_address": "80:F3:DA:4B:2A:DC",
            "mcid": "HP-55-01",
            "category": "Heatpress",
            "model": "HPM 55",
            "location": "Lini 1 - Sublimasi",
            "description": "Pneumatic Double Station Heat Press",
        },
    },
    {
        "device_uid": "90:15:06:B7:AA:08",
        "name": "AF-450 Auto Flat 1",
        "device_type": "ESP32",
        "status": "online",
        "metadata": {
            "mac_address": "90:15:06:B7:AA:08",
            "mcid": "AF-450-01",
            "category": "Heatpress",
            "model": "AF-450",
            "location": "Lini 2 - Flatbed",
            "description": "Automatic Flat Heat Press 450 Series",
        },
    },
    {
        "device_uid": "48:9D:31:2F:B5:18",
        "name": "APM-LOGO Precision 1",
        "device_type": "ESP32",
        "status": "online",
        "metadata": {
            "mac_address": "48:9D:31:2F:B5:18",
            "mcid": "APM-01",
            "category": "Heatpress",
            "model": "APM-LOGO",
            "location": "Lini 3 - Apparel Logo",
            "description": "Auto Positioning Motion Heat Press for Logo & Label",
        },
    },
]


def _ensure_service_api_key(
    client_repo: ClientRepository,
    client: ApiClient,
    raw_key: str,
    key_name: str,
) -> None:
    if not raw_key or not raw_key.strip():
        return
    clean_key = raw_key.strip()
    key_hash = hash_secret_token(clean_key)
    for existing in client.api_keys:
        if existing.key_hash == key_hash:
            return
    client_repo.create_api_key(
        ApiKey(
            client_id=client.id,
            name=key_name,
            key_prefix=clean_key[:16],
            key_hash=key_hash,
        )
    )


def seed_platform_registry(db: Session, seed_iot_fleet: bool = True) -> dict[str, int]:
    """Idempotently seed canonical scopes, roles, and the initial homelab projects & clients."""
    settings = get_settings()
    perm_service = PermissionsService(db)
    perm_service.seed_defaults()

    perm_repo = PermissionsRepository(db)
    project_repo = ProjectRepository(db)
    client_repo = ClientRepository(db)
    db_reg_repo = DatabaseRegistryRepository(db)
    integration_repo = IntegrationRepository(db)
    iot_repo = IotRepository(db)

    projects_created = 0
    clients_created = 0
    devices_seeded = 0

    for item in CONNECTED_PROJECTS_SEED:
        project = project_repo.get_by_slug(item["slug"])
        if not project:
            project = project_repo.create(
                Project(
                    slug=item["slug"],
                    name=item["name"],
                    description=item["description"],
                    status="active",
                )
            )
            projects_created += 1

        client = client_repo.get_by_client_id(item["client_id"])
        scopes = [
            s
            for s_name in item["scopes"]
            if (s := perm_repo.get_scope_by_name(s_name)) is not None
        ]
        if not client:
            client = client_repo.create_client(
                ApiClient(
                    project_id=project.id,
                    client_id=item["client_id"],
                    name=item["client_name"],
                    client_type=item["client_type"],
                    is_active=True,
                    scopes=scopes,
                )
            )
            clients_created += 1

        if item["slug"] == "stock-umkm":
            if not db_reg_repo.get_by_name("stock-umkm-mysql"):
                db_reg_repo.create(
                    DatabaseConnection(
                        project_id=project.id,
                        name="stock-umkm-mysql",
                        engine="mysql",
                        host="100.106.63.90",
                        port=3306,
                        database_name="stock_umkm",
                        username="pap_stock_reader",
                        secret_reference="STOCK_DB_PASSWORD",
                        allowed_tables=["products", "inventories", "categories"],
                        read_only=True,
                        is_active=True,
                    )
                )
            if not integration_repo.get_by_name("stock-umkm-laravel-api"):
                integration_repo.create(
                    Integration(
                        project_id=project.id,
                        name="stock-umkm-laravel-api",
                        integration_type="laravel_api",
                        configuration={"base_url": "http://192.168.25.101:8080/api"},
                        secret_reference="STOCK_UMKM_API_KEY",
                        is_active=True,
                    )
                )

        elif item["slug"] == "personal-server-manager":
            _ensure_service_api_key(
                client_repo,
                client,
                settings.PAP_PSM_SERVICE_KEY,
                "psm-default-service-key",
            )
            if not db_reg_repo.get_by_name("psm-postgresql"):
                db_reg_repo.create(
                    DatabaseConnection(
                        project_id=project.id,
                        name="psm-postgresql",
                        engine="postgresql",
                        host=settings.PSM_DATABASE_HOST,
                        port=settings.PSM_DATABASE_PORT,
                        database_name=settings.PSM_DATABASE_NAME,
                        username=settings.PSM_DATABASE_USER,
                        secret_reference="PSM_DATABASE_PASSWORD",
                        allowed_tables=["servers", "containers", "projects", "deployments", "server_metrics"],
                        read_only=True,
                        is_active=True,
                    )
                )
            if not integration_repo.get_by_name("psm-control-plane-api"):
                integration_repo.create(
                    Integration(
                        project_id=project.id,
                        name="psm-control-plane-api",
                        integration_type="psm_api",
                        configuration={
                            "base_url": settings.PSM_API_URL,
                            "web_url": "http://192.168.25.101:3005",
                            "synced_servers": 1,
                            "synced_containers": 4,
                        },
                        secret_reference="PAP_PSM_SERVICE_KEY",
                        is_active=True,
                    )
                )

        elif item["slug"] == "iot-dashboard":
            _ensure_service_api_key(
                client_repo,
                client,
                settings.PAP_IOT_SERVICE_KEY,
                "iot-dashboard-default-service-key",
            )
            if not integration_repo.get_by_name("iot-dashboard-api"):
                integration_repo.create(
                    Integration(
                        project_id=project.id,
                        name="iot-dashboard-api",
                        integration_type="iot_dashboard",
                        configuration={
                            "base_url": settings.IOT_DASHBOARD_API_URL,
                            "web_url": "http://192.168.25.101:8088",
                            "fleet_category": "Heatpress",
                            "models": ["HPM 55", "AF-450", "APM-LOGO", "comingsoon"],
                        },
                        secret_reference="PAP_IOT_SERVICE_KEY",
                        is_active=True,
                    )
                )
            if seed_iot_fleet:
                for dev_seed in HEATPRESS_FLEET_DEVICES_SEED:
                    existing_dev = iot_repo.get_by_uid(dev_seed["device_uid"])
                    if not existing_dev:
                        created_dev = iot_repo.create_device(
                            Device(
                                project_id=project.id,
                                device_uid=dev_seed["device_uid"],
                                name=dev_seed["name"],
                                device_type=dev_seed["device_type"],
                                status=dev_seed["status"],
                                metadata_json=dev_seed["metadata"],
                            )
                        )
                        _, cred_hash = generate_device_credential()
                        iot_repo.create_credential(
                            DeviceCredential(
                                device_id=created_dev.id,
                                credential_hash=cred_hash,
                            )
                        )
                        devices_seeded += 1

    return {
        "projects_created": projects_created,
        "clients_created": clients_created,
        "devices_seeded": devices_seeded,
    }


