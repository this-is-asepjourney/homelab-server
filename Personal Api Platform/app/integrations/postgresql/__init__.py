"""Controlled PostgreSQL adapter for health checks and allowlisted schema metadata inspection."""

import re
from typing import Any

from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, PermissionDeniedError

IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PostgreSQLAdapter:
    """Least-privilege PostgreSQL metadata and health adapter (no arbitrary SQL endpoint)."""

    def __init__(
        self,
        host: str,
        port: int,
        database_name: str,
        username: str,
        secret_reference: str,
        allowed_tables: list[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.database_name = database_name
        self.username = username
        self.secret_reference = secret_reference
        self.allowed_tables = set(allowed_tables or [])

    def _build_url(self) -> str:
        settings = get_settings()
        password = settings.resolve_secret_reference(self.secret_reference) or ""
        return f"postgresql+psycopg://{self.username}:{password}@{self.host}:{self.port}/{self.database_name}"

    def check_health(self) -> dict[str, Any]:
        settings = get_settings()
        try:
            eng = create_engine(
                self._build_url(),
                pool_pre_ping=True,
                connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
            )
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            eng.dispose()
            return {"reachable": True, "engine": "postgresql", "database": self.database_name}
        except Exception as exc:
            return {
                "reachable": False,
                "engine": "postgresql",
                "database": self.database_name,
                "reason": type(exc).__name__,
            }

    def get_approved_schema(self, table_name: str | None = None) -> dict[str, Any]:
        if table_name is not None:
            if not IDENTIFIER_RE.match(table_name):
                raise BadRequestError(
                    message="Invalid table identifier format",
                    code="INVALID_TABLE_IDENTIFIER",
                )
            if table_name not in self.allowed_tables:
                raise PermissionDeniedError(
                    message=f"Table '{table_name}' is not in the approved schema allowlist",
                    code="TABLE_NOT_ALLOWLISTED",
                )
            target_tables = [table_name]
        else:
            target_tables = sorted(self.allowed_tables)

        settings = get_settings()
        try:
            eng = create_engine(
                self._build_url(),
                connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
            )
            inspector = inspect(eng)
            available = set(inspector.get_table_names())
            tables_meta: dict[str, list[dict[str, Any]]] = {}
            for tbl in target_tables:
                if tbl in available:
                    cols = inspector.get_columns(tbl)
                    tables_meta[tbl] = [
                        {
                            "name": c["name"],
                            "type": str(c["type"]),
                            "nullable": bool(c.get("nullable", True)),
                        }
                        for c in cols
                    ]
                else:
                    tables_meta[tbl] = []
            eng.dispose()
            return {
                "engine": "postgresql",
                "database": self.database_name,
                "allowed_tables": sorted(self.allowed_tables),
                "tables": tables_meta,
            }
        except (BadRequestError, PermissionDeniedError):
            raise
        except Exception:
            return {
                "engine": "postgresql",
                "database": self.database_name,
                "allowed_tables": sorted(self.allowed_tables),
                "tables": {tbl: [] for tbl in target_tables},
                "status": "offline_metadata_only",
            }

