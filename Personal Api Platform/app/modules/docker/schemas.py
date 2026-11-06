"""Pydantic schemas for Docker container metadata and stats."""

from typing import Any

from pydantic import BaseModel


class ContainerSummary(BaseModel):
    id: str
    name: str
    image: str
    state: str
    status: str


class ContainerStats(BaseModel):
    id: str
    cpu_percent: float
    memory_usage_mb: float
    memory_limit_mb: float
    extra: dict[str, Any] = {}

