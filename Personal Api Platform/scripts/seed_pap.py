"""Seed script for initializing PAP scopes, roles, and Phase 3 connected projects."""

from app.core.database import Base, SessionLocal, engine
from app.modules import import_all_models
from app.services.bootstrap import seed_platform_registry


def main() -> None:
    import_all_models()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        result = seed_platform_registry(db)
        print(f"Bootstrap complete: {result}")


if __name__ == "__main__":
    main()

