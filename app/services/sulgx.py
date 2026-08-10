import asyncio
import aiohttp
import json
import logging
from app import config

logger = logging.getLogger(__name__)

class SulgXClient:
    def __init__(self):
        self.base_url = config.SULGX_URL
        self.password = config.SULGX_PASSWORD
        self._cookie = None
        self._session = None
        self._login_lock = asyncio.Lock()
        self._last_login_ts = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_login(self, session: aiohttp.ClientSession):
        """Login only once, reuse cookie. Retry on 429 with backoff."""
        if self._cookie:
            return True

        async with self._login_lock:
            if self._cookie:
                return True

            url = f"{self.base_url}/api/login"
            payload = {"password": self.password}
            max_attempts = 4
            for attempt in range(max_attempts):
                try:
                    async with session.post(url, json=payload, timeout=10) as resp:
                        if resp.status == 200:
                            cookie_header = resp.headers.get("Set-Cookie")
                            if cookie_header:
                                self._cookie = cookie_header.split(";")[0]
                                return True
                            logger.error("Login 200 but no cookie")
                            return False
                        elif resp.status == 429:
                            wait = 1.5 * (attempt + 1)
                            logger.warning(f"Rate limited (429), retrying in {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        else:
                            logger.error(f"SulgX login failed status={resp.status}")
                            return False
                except asyncio.TimeoutError:
                    logger.warning("Login timeout, retrying...")
                    await asyncio.sleep(1)
                    continue
            return False

    async def _request(self, method: str, path: str, payload: dict = None, retries: int = 3):
        """Make authenticated request with login retry and 429 handling."""
        session = await self._get_session()
        for attempt in range(retries):
            ok = await self._ensure_login(session)
            if not ok:
                await asyncio.sleep(1)
                continue

            headers = {"Cookie": self._cookie} if self._cookie else {}
            url = f"{self.base_url}{path}"
            try:
                kwargs = {}
                if payload is not None:
                    kwargs["json"] = payload
                async with session.request(method.upper(), url, headers=headers, timeout=15, **kwargs) as resp:
                    if resp.status == 200 or resp.status == 201:
                        if resp.content_type == "application/json":
                            try:
                                return await resp.json()
                            except json.JSONDecodeError:
                                return {"ok": True}
                        return {"ok": True}
                    elif resp.status == 401:
                        # Session expired, relogin and retry
                        self._cookie = None
                        await asyncio.sleep(0.5)
                        continue
                    elif resp.status == 429:
                        wait = 1.5 * (attempt + 1)
                        logger.warning(f"Rate limited (429) on {path}, retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        logger.error(f"Request {method} {path} failed status={resp.status}")
                        return None
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on {method} {path}, retrying...")
                await asyncio.sleep(1)
                continue
            except aiohttp.ClientError as e:
                logger.error(f"Client error on {method} {path}: {e}")
                return None
        return None

    async def create_link(self, label: str, limit_gb: float = 0, days_valid: int = 0) -> dict:
        data = await self._request("POST", "/api/links", {
            "label": label,
            "limit_value": limit_gb,
            "limit_unit": "GB",
            "max_connections": 0,
            "days_valid": days_valid
        })
        if data and "uuid" in data:
            uuid = data["uuid"]
            data["subscription_url"] = f"{self.base_url}/sub/{uuid}"
            return data
        return None

    async def get_link(self, uuid: str) -> dict:
        data = await self._request("GET", "/api/links")
        if data and "links" in data:
            for link in data["links"]:
                if link.get("uuid") == uuid:
                    link["subscription_url"] = f"{self.base_url}/sub/{uuid}"
                    return link
        return None

    async def set_link_status(self, uuid: str, active: bool) -> bool:
        data = await self._request("PATCH", f"/api/links/{uuid}", {"active": active})
        return data is not None

    async def delete_link(self, uuid: str) -> bool:
        data = await self._request("DELETE", f"/api/links/{uuid}")
        return data is not None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

sulgx_client = SulgXClient()