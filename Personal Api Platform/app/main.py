"""FastAPI application entry point for Personal API Platform (PAP) & Unified Homelab Core Gateway."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextAndSecurityMiddleware
from app.modules import import_all_models
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.backups.router import router as backups_router
from app.modules.clients.router import router as clients_router
from app.modules.database_registry.router import router as database_router
from app.modules.docker.router import router as docker_router
from app.modules.integrations.router import router as integrations_router
from app.modules.iot.fleet_router import compat_devices_router, v1_fleet_router
from app.modules.iot.router import router as iot_router
from app.modules.metrics.router import router as metrics_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.permissions.router import router as permissions_router
from app.modules.projects.router import router as projects_router
from app.modules.server.router import router as server_router
from app.modules.users.router import router as users_router
from app.modules.webhooks.router import router as webhooks_router
from app.services.bootstrap import seed_platform_registry

# Direct imports for unified PSM control plane
try:
    from apps.api.app.api.v1.router import api_router as psm_api_router
    from apps.api.app.main import init_db as init_psm_db
    from apps.api.app.websocket.handlers import ws_router as psm_ws_router
    HAS_PSM_DIRECT = True
except Exception as e:
    HAS_PSM_DIRECT = False
    psm_api_router = None
    psm_ws_router = None
    init_psm_db = None
    print(f"[PAP Gateway] Note on PSM direct router load: {e}")


@asynccontextmanager
async def _lifespan(application: FastAPI):
    # 1. Initialize PAP Core Database
    try:
        import_all_models()
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_platform_registry(db)
    except Exception as e:
        print(f"[PAP Core] Startup notice: {e}")

    # 2. Initialize PSM Database (auto-creates 'psm' PostgreSQL db and seeds homelab)
    if HAS_PSM_DIRECT and init_psm_db:
        try:
            init_psm_db()
            print("[PAP Core] PSM Control Plane database & schema ready.")
        except Exception as e:
            print(f"[PAP Core] PSM DB init notice: {e}")

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(debug=settings.APP_DEBUG)
    import_all_models()

    application = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Central Core API Gateway & Management Platform for Homelab Server, "
            "PSM Control Plane, IoT Devices, Database Registry, and Disaster Recovery Backups."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Device-Credential", "X-Request-ID"],
    )
    application.add_middleware(RequestContextAndSecurityMiddleware)

    register_exception_handlers(application)

    # ── Root Endpoints ─────────────────────────────────────────────────────────
    # System info, health, and prometheus metrics
    application.include_router(server_router)
    # IoT Dashboard direct compatibility routes (/api/devices/*, /api/health)
    application.include_router(compat_devices_router)

    # PSM WebSockets (/ws/servers/..., /ws/deployments/...)
    if HAS_PSM_DIRECT and psm_ws_router:
        application.include_router(psm_ws_router)

    # ── Versioned API v1 Router (/api/v1/...) ──────────────────────────────────
    api_v1 = APIRouter(prefix=settings.API_PREFIX)
    api_v1.include_router(server_router)
    api_v1.include_router(auth_router)
    api_v1.include_router(backups_router)  # Unified Backup & Disaster Recovery
    api_v1.include_router(users_router)
    api_v1.include_router(permissions_router)
    api_v1.include_router(projects_router)
    api_v1.include_router(clients_router)
    api_v1.include_router(database_router)
    api_v1.include_router(integrations_router)
    api_v1.include_router(v1_fleet_router)
    api_v1.include_router(iot_router)
    api_v1.include_router(metrics_router)
    api_v1.include_router(monitoring_router)
    api_v1.include_router(docker_router)
    api_v1.include_router(webhooks_router)
    api_v1.include_router(audit_router)

    application.include_router(api_v1)

    # ── PSM Control Plane Direct Integration ───────────────────────────────────
    if HAS_PSM_DIRECT and psm_api_router:
        # Mount PSM endpoints directly under /api/v1 (servers, agents, containers, deployments, etc.)
        application.include_router(psm_api_router, prefix="/api/v1")
        # Also alias under /psm/api/v1 and /psm for seamless proxy backward compatibility
        application.include_router(psm_api_router, prefix="/psm/api/v1")

    # ── Mission Control Web Management UI ──────────────────────────────────────
    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    async def serve_mission_control_ui():
        ui_file = Path(__file__).parent / "ui" / "index.html"
        if ui_file.exists():
            return HTMLResponse(content=ui_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>PAP Core Gateway Running</h1><p><a href='/docs'>Swagger API Docs</a></p>")

    # ── Agent Setup Script ─────────────────────────────────────────────────────
    @application.get("/install-agent.sh", include_in_schema=False)
    async def install_agent_script():
        script_content = """#!/usr/bin/env bash
set -e
echo "========================================="
echo "Personal Server Manager (PSM) Agent Setup"
echo "========================================="

if [ -z "$PSM_SERVER_ID" ] || [ -z "$PSM_TOKEN" ]; then
  echo "Error: PSM_SERVER_ID and PSM_TOKEN environment variables are required."
  exit 1
fi

PSM_CONTROL_PLANE="${PSM_CONTROL_PLANE:-http://localhost:8000}"
INSTALL_DIR="/opt/psm/agent"

echo "Target Control Plane: $PSM_CONTROL_PLANE"
echo "Server ID: $PSM_SERVER_ID"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

cat <<EOF > agent.env
SERVER_ID=$PSM_SERVER_ID
AGENT_TOKEN=$PSM_TOKEN
CONTROL_PLANE_URL=$PSM_CONTROL_PLANE
EOF

echo "PSM Agent configured successfully at $INSTALL_DIR/agent.env"
"""
        return Response(content=script_content, media_type="text/x-shellscript")

    return application


app = create_app()
