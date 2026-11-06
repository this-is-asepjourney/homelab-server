"""Pydantic schemas for system health, readiness, and platform info."""

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str = "healthy"
    service: str = "personal-api-platform"


class SystemInfo(BaseModel):
    name: str
    architecture: str
    version: str
    api_prefix: str
    network_scope: str
    modules: list[str]

