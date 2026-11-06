"""PAP domain modules and ORM model discovery."""


def import_all_models() -> None:
    """Import all SQLAlchemy models so Base.metadata is fully populated for Alembic and tests."""
    from app.modules.audit import models as _audit_models  # noqa: F401
    from app.modules.auth import models as _auth_models  # noqa: F401
    from app.modules.clients import models as _clients_models  # noqa: F401
    from app.modules.database_registry import models as _db_models  # noqa: F401
    from app.modules.integrations import models as _integration_models  # noqa: F401
    from app.modules.iot import models as _iot_models  # noqa: F401
    from app.modules.permissions import models as _perm_models  # noqa: F401
    from app.modules.projects import models as _proj_models  # noqa: F401
    from app.modules.users import models as _user_models  # noqa: F401
    from app.modules.webhooks import models as _webhook_models  # noqa: F401
