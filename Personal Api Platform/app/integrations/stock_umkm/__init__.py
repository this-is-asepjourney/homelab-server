"""Stock UMKM (Laravel) and POS Cashier business integration adapter."""

from typing import Any, Optional

import httpx

from app.core.config import get_settings


class StockUmkmAdapter:
    """Adapter for Stock UMKM Laravel API with controlled fallback catalogue for homelab development."""

    DEFAULT_PRODUCTS: list[dict[str, Any]] = [
        {
            "product_id": "101",
            "sku": "UMKM-KOPI-001",
            "name": "Kopi Arabika Gayo 250g",
            "category": "Beverages",
            "unit_price": 65000,
            "currency": "IDR",
            "is_active": True,
        },
        {
            "product_id": "102",
            "sku": "UMKM-TEH-002",
            "name": "Teh Hijau Melati 100g",
            "category": "Beverages",
            "unit_price": 32000,
            "currency": "IDR",
            "is_active": True,
        },
        {
            "product_id": "123",
            "sku": "UMKM-GULA-003",
            "name": "Gula Aren Organik 500g",
            "category": "Ingredients",
            "unit_price": 45000,
            "currency": "IDR",
            "is_active": True,
        },
    ]

    DEFAULT_INVENTORY: list[dict[str, Any]] = [
        {
            "product_id": "101",
            "sku": "UMKM-KOPI-001",
            "warehouse": "main",
            "quantity": 40,
            "reserved": 2,
            "available": 38,
        },
        {
            "product_id": "102",
            "sku": "UMKM-TEH-002",
            "warehouse": "main",
            "quantity": 18,
            "reserved": 0,
            "available": 18,
        },
        {
            "product_id": "123",
            "sku": "UMKM-GULA-003",
            "warehouse": "main",
            "quantity": 25,
            "reserved": 0,
            "available": 25,
        },
    ]

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key_ref: str = "STOCK_UMKM_API_KEY",
        timeout: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.STOCK_UMKM_API_URL).rstrip("/")
        self.api_key = settings.resolve_secret_reference(api_key_ref) or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key and self.api_key != "REPLACE_ME":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def check_health(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/health", headers=self._headers())
                return {
                    "service": "stock_umkm",
                    "reachable": resp.status_code < 500,
                    "status_code": resp.status_code,
                }
        except Exception:
            return {
                "service": "stock_umkm",
                "reachable": False,
                "mode": "local_adapter_fallback",
            }

    def list_products(
        self,
        search: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        products = [dict(item) for item in self.DEFAULT_PRODUCTS]
        if product_id:
            products = [p for p in products if p["product_id"] == product_id]
        if search:
            q = search.lower()
            products = [
                p
                for p in products
                if q in p["name"].lower() or q in p["sku"].lower()
            ]
        return products

    def list_inventory(self, product_id: Optional[str] = None) -> list[dict[str, Any]]:
        items = [dict(item) for item in self.DEFAULT_INVENTORY]
        if product_id:
            items = [i for i in items if i["product_id"] == product_id]
        return items

