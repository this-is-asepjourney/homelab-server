"""Structured logging and secret redaction utilities."""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any
import uuid

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "client_secret",
        "jwt_secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "raw_key",
        "credential",
        "raw_credential",
        "authorization",
        "x-api-key",
        "x-device-credential",
        "stock_db_password",
        "psm_database_password",
        "mqtt_password",
    }
)

SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api_key|credential|authorization)([\s:=]+['\"]?)([^'\"\s,&]+)"
)


def get_request_id() -> str:
    req_id = request_id_ctx_var.get()
    if not req_id:
        req_id = str(uuid.uuid4())
        request_id_ctx_var.set(req_id)
    return req_id


def set_request_id(req_id: str) -> None:
    request_id_ctx_var.set(req_id)


def redact_value(data: Any) -> Any:
    """Recursively redact sensitive fields from dicts, lists, and strings."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS or any(
                s in str(k).lower() for s in ("password", "secret", "token", "api_key", "credential")
            ):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = redact_value(v)
        return sanitized
    if isinstance(data, list):
        return [redact_value(item) for item in data]
    if isinstance(data, str):
        return SECRET_PATTERN.sub(r"\1\2***REDACTED***", data)
    return data


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter with request ID and automatic secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        message = SECRET_PATTERN.sub(r"\1\2***REDACTED***", record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx_var.get() or None,
            "message": message,
        }
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            payload["context"] = redact_value(record.extra_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(debug: bool = False) -> logging.Logger:
    logger = logging.getLogger("pap")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = configure_logging()

