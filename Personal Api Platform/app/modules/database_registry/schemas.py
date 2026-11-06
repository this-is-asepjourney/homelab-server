"""Pydantic schemas for database connection registration and schema metadata."""

from datetime import datetime
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

SECRET_REF_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


class DatabaseConnectionCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=128)
    engine: str = Field(..., pattern=r"^(postgresql|mysql)$")
    host: str = Field(default="100.106.63.90", min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(..., min_length=1, max_length=128)
    username: str = Field(..., min_length=1, max_length=128)
    secret_reference: str = Field(
        ...,
        description="Environment variable reference name (e.g. STOCK_DB_PASSWORD); never plaintext secret.",
    )
    allowed_tables: list[str] = Field(default_factory=list)
    read_only: bool = True

    @field_validator("secret_reference")
    @classmethod
    def validate_secret_reference_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not SECRET_REF_RE.match(cleaned):
            raise ValueError(
                "secret_reference must be an uppercase environment variable key (e.g. STOCK_DB_PASSWORD), not a raw password."
            )
        return cleaned

    @field_validator("username")
    @classmethod
    def reject_privileged_username(cls, v: str) -> str:
        cleaned = v.strip()
        if cleaned.lower() in ("root", "postgres", "superuser"):
            raise ValueError(
                f"Privileged database account '{cleaned}' is forbidden; use a dedicated least-privilege role."
            )
        return cleaned

    @field_validator("allowed_tables")
    @classmethod
    def validate_table_names(cls, tables: list[str]) -> list[str]:
        for t in tables:
            if not TABLE_NAME_RE.match(t):
                raise ValueError(f"Invalid table identifier in allowlist: '{t}'")
        return tables


class DatabaseConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    engine: str
    host: str
    port: int
    database_name: str
    username: str
    secret_reference: str
    allowed_tables: list[str]
    read_only: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

