"""Pytest fixtures for isolated in-memory database, seeded RBAC, and TestClient."""

from collections.abc import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, build_engine, get_db
from app.core.middleware import rate_limiter
from app.main import create_app
from app.modules import import_all_models
from app.modules.permissions.service import PermissionsService
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    import_all_models()
    test_engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = TestingSessionLocal()
    PermissionsService(session).seed_defaults()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    rate_limiter.reset()
    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_token(client: TestClient, db_session: Session) -> str:
    user_service = UserService(db_session)
    user_service.create_user(
        UserCreate(
            email="admin@homelab.local",
            password="StrongAdminPassword!123",
            full_name="Homelab Admin",
            roles=["admin"],
        )
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@homelab.local", "password": "StrongAdminPassword!123"},
    )
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


@pytest.fixture()
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}

