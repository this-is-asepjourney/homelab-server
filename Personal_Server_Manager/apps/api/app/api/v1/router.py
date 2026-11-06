from fastapi import APIRouter
from apps.api.app.api.v1.auth import router as auth_router
from apps.api.app.api.v1.servers import router as servers_router
from apps.api.app.api.v1.agents import router as agents_router
from apps.api.app.api.v1.containers import router as containers_router
from apps.api.app.api.v1.projects import router as projects_router
from apps.api.app.api.v1.deployments import router as deployments_router
from apps.api.app.api.v1.monitoring import router as monitoring_router
from apps.api.app.api.v1.audit import router as audit_router
from apps.api.app.api.v1.users import router as users_router
from apps.api.app.api.v1.backups import router as backups_router
from apps.api.app.api.v1.templates import router as templates_router
from apps.api.app.api.v1.notifications import router as notifications_router
from apps.api.app.api.v1.pap_integration import router as pap_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(servers_router)
api_router.include_router(agents_router)
api_router.include_router(containers_router)
api_router.include_router(projects_router)
api_router.include_router(deployments_router)
api_router.include_router(monitoring_router)
api_router.include_router(audit_router)
api_router.include_router(users_router)
api_router.include_router(backups_router)
api_router.include_router(templates_router)
api_router.include_router(notifications_router)
api_router.include_router(pap_router)
