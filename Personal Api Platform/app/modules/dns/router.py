"""FastAPI router for Local DNS & Virtual Host Manager."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.modules.dns.service import DnsService

router = APIRouter(prefix="/dns", tags=["Local DNS & Virtual Hosts"])


class RegisterDomainRequest(BaseModel):
    domain: str = Field(..., description="Local domain, e.g. pos-kasir.homelab")
    target_port: int = Field(..., description="Target port of the container, e.g. 3000")
    target_host: Optional[str] = Field(default="host.docker.internal", description="Target host IP or hostname")
    project_name: Optional[str] = Field(default=None, description="Optional project identifier")


@router.get("/status")
def get_dns_status():
    """Returns the live reachability status of Local DNS (:53) and Ingress Gateway (:80)."""
    return {"success": True, "data": DnsService.check_dns_status()}


@router.get("/records")
def list_dns_records():
    """Lists all active local domains, categories, and target port mappings."""
    domains = DnsService.list_domains()
    return {
        "success": True,
        "count": len(domains),
        "data": domains,
    }


@router.post("/records", status_code=status.HTTP_201_CREATED)
def register_domain(payload: RegisterDomainRequest):
    """Registers a new virtual host routing and adds DNS mapping."""
    try:
        res = DnsService.register_domain_route(
            domain=payload.domain,
            target_port=payload.target_port,
            target_host=payload.target_host or "host.docker.internal",
            project_name=payload.project_name,
        )
        return {"success": True, "message": f"Domain {payload.domain} registered successfully", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register domain: {e}")


@router.delete("/records/{domain}")
def delete_domain(domain: str):
    """Deletes a custom domain route and cleans up virtual host config."""
    removed = DnsService.remove_domain_route(domain)
    if not removed:
        raise HTTPException(status_code=404, detail="Domain not found or is a protected system domain")
    return {"success": True, "message": f"Domain {domain} removed successfully"}


@router.get("/hosts-file")
def download_hosts_file():
    """Returns ready-to-copy /etc/hosts or Windows hosts file format."""
    text_content = DnsService.generate_hosts_file_content()
    return Response(
        content=text_content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=homelab_hosts.txt"},
    )

