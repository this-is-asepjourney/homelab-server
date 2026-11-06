"""FastAPI application entry point for Personal API Platform (PAP)."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextAndSecurityMiddleware
from app.modules import import_all_models
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
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


@asynccontextmanager
async def _lifespan(application: FastAPI):
    try:
        import_all_models()
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_platform_registry(db)
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(debug=settings.APP_DEBUG)
    import_all_models()

    application = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Self-hosted Modular Monolith integration platform for applications, "
            "IoT devices, databases, and homelab infrastructure."
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

    # Mount root system endpoints (/health, /ready, /system/info, /system/version, /metrics)
    application.include_router(server_router)
    # Mount IoT Dashboard direct compatibility routes (/api/devices/*, /api/health)
    application.include_router(compat_devices_router)

    # Mount versioned API v1 router (/api/v1/...)
    api_v1 = APIRouter(prefix=settings.API_PREFIX)
    api_v1.include_router(server_router)
    api_v1.include_router(auth_router)
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
    return application


app = create_app()

