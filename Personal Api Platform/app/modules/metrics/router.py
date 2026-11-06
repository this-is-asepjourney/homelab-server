"""HTTP router for server metrics and Prometheus query endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.permissions import Principal
from app.dependencies import require_any_scope, require_scopes
from app.modules.metrics.service import MetricsService
from app.schemas import success_response

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/server")
def get_server_metrics(
    principal: Principal = Depends(require_any_scope("server:read", "metrics:read")),
):
    service = MetricsService()
    return success_response(
        data=service.get_server_metrics(),
        message="Server metrics retrieved successfully",
    )


@router.get("/prometheus/query")
def prometheus_instant_query(
    query: str = Query(..., min_length=1, max_length=512),
    time: Optional[str] = Query(default=None),
    principal: Principal = Depends(require_scopes("metrics:read")),
):
    service = MetricsService()
    data = service.query_instant(query=query, time_param=time)
    return success_response(
        data=data,
        message="Prometheus instant query executed successfully",
    )


@router.get("/prometheus/range")
def prometheus_range_query(
    query: str = Query(..., min_length=1, max_length=512),
    start: str = Query(..., min_length=1),
    end: str = Query(..., min_length=1),
    step: str = Query(default="60s"),
    principal: Principal = Depends(require_scopes("metrics:read")),
):
    service = MetricsService()
    data = service.query_range(query=query, start=start, end=end, step=step)
    return success_response(
        data=data,
        message="Prometheus range query executed successfully",
    )


@router.get("/prometheus/targets")
def prometheus_targets(
    principal: Principal = Depends(require_scopes("metrics:read")),
):
    service = MetricsService()
    data = service.get_targets()
    return success_response(
        data=data,
        message="Prometheus scrape targets retrieved successfully",
    )

