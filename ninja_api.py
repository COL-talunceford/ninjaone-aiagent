import time
from typing import Any, Dict, Optional

import httpx
from config import settings

class NinjaClient:
    """
    Lightweight NinjaOne API client (OAuth2 client-credentials).
    Tokens are cached until ~60s before expiry.
    Adjust endpoint paths to your tenant's Public API documentation if needed.
    """

    def __init__(self):
        self.base_url = settings.NINJA_BASE_URL
        self.auth_url = settings.NINJA_AUTH_URL
        self.client_id = settings.NINJA_CLIENT_ID
        self.client_secret = settings.NINJA_CLIENT_SECRET
        self.scope = settings.NINJA_SCOPE
        self._token: Optional[str] = None
        self._expiry: float = 0.0

    async def _ensure_token(self) -> None:
        if self._token and time.time() < self._expiry - 60:
            return
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(self.auth_url, data=data)
            r.raise_for_status()
            tok = r.json()
            self._token = tok["access_token"]
            self._expiry = time.time() + int(tok.get("expires_in", 3600))

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _get(self, path: str, params: Dict[str, Any] | None = None) -> Any:
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, json: Dict[str, Any]) -> Any:
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base_url}{path}", headers=self._headers(), json=json)
            r.raise_for_status()
            return r.json() if r.content else {}

    async def _patch(self, path: str, json: Dict[str, Any]) -> Any:
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.patch(f"{self.base_url}{path}", headers=self._headers(), json=json)
            r.raise_for_status()
            return r.json() if r.content else {}

    # --------------------
    # Example endpoints
    # --------------------
    async def list_devices(self, limit: int = 50, offset: int = 0) -> Any:
        return await self._get("/api/v2/devices/detailed", params={"limit": limit, "offset": offset})

    async def get_device(self, device_id: int) -> Any:
        return await self._get(f"/api/v2/devices/{device_id}")

    async def update_ticket(self, ticket_id: int, body: Dict[str, Any]) -> Any:
        return await self._patch(f"/api/v2/tickets/{ticket_id}", json=body)

    async def add_ticket_comment(self, ticket_id: int, note: str, is_public: bool = False) -> Any:
        payload = { "comments": [ { "isPublic": is_public, "text": note } ] }
        return await self.update_ticket(ticket_id, payload)

    async def run_script(self, device_id: int, script_id: int, params: Dict[str, Any] | None = None) -> Any:
        payload = {"type": "SCRIPT", "id": script_id, "parameters": params or {}}
        return await self._post(f"/api/v2/devices/{device_id}/script/run", json=payload)

