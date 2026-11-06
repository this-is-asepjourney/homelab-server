"""HTTP middlewares for request ID tracking, structured logging, security headers, and rate limiting."""

from collections import defaultdict, deque
import threading
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import build_error_payload
from app.core.logging import logger, set_request_id


class SlidingWindowRateLimiter:
    """Thread-safe in-memory per-client sliding-window rate limiter."""

    def __init__(self, max_requests: int = 120, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._hits[client_key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - q[0])))
                return False, retry_after
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = SlidingWindowRateLimiter(
    max_requests=get_settings().RATE_LIMIT_REQUESTS_PER_MINUTE,
    window_seconds=60,
)


def _extract_client_key(request: Request) -> str:
    """Identify the caller by API key prefix, Authorization token hash prefix, or client IP."""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key[:16]}"
    auth = request.headers.get("Authorization")
    if auth:
        return f"auth:{auth[-16:]}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


class RequestContextAndSecurityMiddleware(BaseHTTPMiddleware):
    """Assigns validated UUID request IDs, enforces rate limits, logs requests, and sets security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_req_id = request.headers.get("X-Request-ID", "")
        try:
            validated_id = str(uuid.UUID(incoming_req_id))
        except ValueError:
            validated_id = str(uuid.uuid4())

        set_request_id(validated_id)
        start_time = time.perf_counter()

        # Skip rate limiting for liveness/readiness probes
        if request.url.path not in ("/health", "/ready", "/api/v1/health", "/api/v1/ready"):
            client_key = _extract_client_key(request)
            allowed, retry_after = rate_limiter.is_allowed(client_key)
            if not allowed:
                payload = build_error_payload(
                    message="Too many requests; rate limit exceeded",
                    code="RATE_LIMIT_EXCEEDED",
                    details={"retry_after_seconds": retry_after},
                )
                return JSONResponse(
                    status_code=429,
                    content=payload,
                    headers={
                        "X-Request-ID": validated_id,
                        "Retry-After": str(retry_after),
                    },
                )

        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers["X-Request-ID"] = validated_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"

        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response

