"""HTTP / fake client for the existing Divar assisted-pilot service.

Upstream project: C:\\taha\\projects\\divar
Safety: never auto-login, never solve captcha, never click final submit.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class DivarClient(Protocol):
    async def health(self) -> dict[str, Any]: ...

    async def create_product(self, product: dict[str, Any]) -> dict[str, Any]: ...

    async def create_task(self, product_id: str) -> dict[str, Any]: ...

    async def get_prefill(self, task_id: str) -> dict[str, Any]: ...

    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]: ...


class FakeDivarClient:
    """In-memory stand-in matching the Divar pilot API shape (for tests / offline)."""

    def __init__(self) -> None:
        self.products: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self._seq = 0

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "mode": "fake", "products": len(self.products)}

    async def create_product(self, product: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        pid = product.get("id") or f"CM-P{self._seq:04d}"
        stored = {
            "id": pid,
            "title": product["title"],
            "description": product.get("description") or "",
            "price": int(product.get("price") or 0),
            "category": product.get("category") or "vehicles",
            "attributes": product.get("attributes") or {},
            "images": product.get("images") or [],
            "city": product.get("city") or "تهران",
            "status": "active",
            "external_vehicle_id": product.get("external_vehicle_id"),
        }
        self.products[pid] = stored
        return {"product": stored}

    async def create_task(self, product_id: str) -> dict[str, Any]:
        if product_id not in self.products:
            raise ValueError("محصول پیدا نشد.")
        self._seq += 1
        tid = f"TASK-CM-{self._seq:04d}"
        product = self.products[product_id]
        attrs = product.get("attributes") or {}
        validation_errors = []
        for field, label in [
            ("brand", "برند"),
            ("model", "مدل"),
            ("year", "سال ساخت"),
        ]:
            if not attrs.get(field):
                validation_errors.append({"field": f"attributes.{field}", "message": f"مقدار الزامی «{label}» وارد نشده است."})
        if not product.get("images"):
            validation_errors.append({"field": "images", "message": "مقدار الزامی «تصاویر» وارد نشده است."})
        status = "needs_review" if validation_errors else "ready_for_assignment"
        task = {
            "id": tid,
            "productId": product_id,
            "category": product.get("category"),
            "status": status,
            "validationErrors": validation_errors,
            "payload": {
                "title": product["title"],
                "description": product["description"],
                "price": product["price"],
                "attributes": attrs,
                "images": product.get("images") or [],
            },
        }
        self.tasks[tid] = task
        return {"task": task}

    async def get_prefill(self, task_id: str) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"وظیفه «{task_id}» پیدا نشد.")
        return {
            "prefill": {
                "taskId": task["id"],
                "category": task.get("category"),
                "status": task.get("status"),
                "fields": task.get("payload"),
                "validationErrors": task.get("validationErrors") or [],
            }
        }

    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.tasks.values())
        if status:
            rows = [t for t in rows if t.get("status") == status]
        return rows


class HttpDivarClient:
    """Talks to the Node Divar pilot at DIVAR_API_BASE (default localhost:3000)."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.divar_api_base).rstrip("/")
        self.token = token if token is not None else settings.divar_api_token
        self.last_error: str | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Up to 3 attempts. Last failure text is kept on last_error."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
                    )
                if response.status_code >= 500 and attempt < 2:
                    self.last_error = response.text[:300]
                    continue
                self.last_error = None if response.status_code < 400 else response.text[:300]
                return response
            except httpx.HTTPError as exc:
                last_exc = exc
                self.last_error = str(exc)[:300]
        raise last_exc or RuntimeError(self.last_error or "divar request failed")

    async def health(self) -> dict[str, Any]:
        r = await self._request("GET", "/api/health")
        r.raise_for_status()
        return r.json()

    async def create_product(self, product: dict[str, Any]) -> dict[str, Any]:
        r = await self._request("POST", "/api/products", json=product)
        if r.status_code >= 400:
            raise ValueError(self.last_error or r.text)
        return r.json()

    async def create_task(self, product_id: str) -> dict[str, Any]:
        r = await self._request("POST", "/api/tasks", json={"productId": product_id})
        if r.status_code >= 400:
            raise ValueError(self.last_error or r.text)
        return r.json()

    async def get_prefill(self, task_id: str) -> dict[str, Any]:
        r = await self._request("GET", f"/api/tasks/{task_id}/prefill")
        if r.status_code >= 400:
            raise ValueError(self.last_error or r.text)
        return r.json()

    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {"status": status} if status else {}
        r = await self._request("GET", "/api/tasks", params=params)
        r.raise_for_status()
        return r.json().get("tasks") or []


_fake_singleton: FakeDivarClient | None = None


def get_divar_client() -> DivarClient:
    settings = get_settings()
    if settings.divar_mode == "http":
        return HttpDivarClient()
    global _fake_singleton
    if _fake_singleton is None:
        _fake_singleton = FakeDivarClient()
    return _fake_singleton


def reset_fake_divar_client() -> FakeDivarClient:
    """Test helper — fresh fake store."""
    global _fake_singleton
    _fake_singleton = FakeDivarClient()
    return _fake_singleton
