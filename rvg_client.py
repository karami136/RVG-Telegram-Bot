import os
import httpx

class RVGError(Exception):
    pass

class RVGClient:
    def __init__(self):
        self.base = os.environ["RVG_BASE_URL"].rstrip("/")
        self.key = os.environ["RVG_BOT_API_KEY"].strip()

    def headers(self):
        return {"X-RVG-Bot-Key": self.key}

    async def health(self):
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(self.base + "/api/bot/health", headers=self.headers())
        if r.status_code >= 400:
            raise RVGError(f"RVG HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    async def create_config(self, *, label: str, volume_gb: int, days: int, protocol="vless-ws"):
        payload = {
            "label": label[:60],
            "limit_value": volume_gb,
            "limit_unit": "GB",
            "expires_days": days,
            "protocol": protocol,
            "fingerprint": "chrome",
            "alpn": "h2,http/1.1",
        }
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as c:
            r = await c.post(self.base + "/api/bot/links",
                             headers=self.headers(), json=payload)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise RVGError(f"RVG HTTP {r.status_code}: {detail}")
        return r.json()

    async def get_config(self, uuid: str):
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{self.base}/api/bot/links/{uuid}", headers=self.headers())
        if r.status_code >= 400:
            raise RVGError(f"RVG HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    async def disable_config(self, uuid: str):
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.delete(f"{self.base}/api/bot/links/{uuid}", headers=self.headers())
        if r.status_code >= 400:
            raise RVGError(f"RVG HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    async def renew_config(self, uuid: str, days: int = 30):
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self.base}/api/bot/links/{uuid}/renew",
                headers=self.headers(), json={"days": days}
            )
        if r.status_code >= 400:
            raise RVGError(f"RVG HTTP {r.status_code}: {r.text[:500]}")
        return r.json()
