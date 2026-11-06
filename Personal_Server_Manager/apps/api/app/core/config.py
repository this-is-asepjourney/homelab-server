import os
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Personal Server Manager (PSM)"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "b8f36a89270df8417727e025170d1fa78f5f4d8520857ef51fa930f785b96a4e")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours in dev
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Fernet master key for secret environment variables (must be 32 url-safe base64-encoded bytes)
    ENCRYPTION_MASTER_KEY: str = os.getenv(
        "ENCRYPTION_MASTER_KEY", "uO1HwXG9J5vYyZl3eQ0f9T_m0K8xW-4jR2hD8qV7sLA="
    )

    # PostgreSQL Configuration (Personal Server Manager Database)
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "psm")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "appuser")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "admin12345")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "100.106.63.90")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))

    # Database: defaults to PostgreSQL if DATABASE_URL or POSTGRES_HOST is reachable, fallbacks to SQLite for local unit tests
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./psm.db"
    )

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3005",
        "http://localhost:8088",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3005",
        "http://127.0.0.1:8088",
        "http://localhost:8000",
        "http://192.168.25.101:3005",
        "http://192.168.25.101:8000",
        "http://192.168.25.101:8088",
        "http://100.106.63.90:3005",
        "http://100.106.63.90:8000",
        "http://100.106.63.90:8001",
        "http://100.106.63.90:8088",
    ]

    # Personal API Platform (Main API / API Utama) & IoT Dashboard Integration
    PAP_API_URL: str = os.getenv("PAP_API_URL", "http://192.168.25.101:8000")
    PAP_API_KEY: str = os.getenv("PAP_API_KEY", "pap_key_psm_control_plane_default_secret_key_2026")
    IOT_DASHBOARD_URL: str = os.getenv("IOT_DASHBOARD_URL", "http://192.168.25.101:8088")

    # Storage & Workspace paths
    STORAGE_BASE_DIR: str = os.getenv("STORAGE_BASE_DIR", "./storage")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./storage/uploads")
    RELEASE_DIR: str = os.getenv("RELEASE_DIR", "./storage/releases")

    # Agent Heartbeat & Offline threshold (seconds)
    HEARTBEAT_TIMEOUT_SECONDS: int = 45

    model_config = {
        "env_file": (".env.example", ".env"),
        "extra": "ignore"
    }


settings = Settings()

# Ensure storage directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.RELEASE_DIR, exist_ok=True)
