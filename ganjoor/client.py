import asyncio
import sys
import time
from typing import Any

import httpx

_BASE = "https://api.ganjoor.net"
_RATE_LIMIT = 1.0         # minimum seconds between requests
_BACKOFF = (5, 15, 45)   # retry delays for server errors (429/5xx)
_CONNECTIVITY_RETRY = 30  # seconds to wait between connectivity retries

_last_request_time: float = 0.0


class GanjoorClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GanjoorClient":
        self._http = httpx.AsyncClient(timeout=30)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    async def _get(self, path: str) -> Any | None:
        global _last_request_time
        url = _BASE + path
        server_attempts = 0

        while True:
            gap = _last_request_time + _RATE_LIMIT - time.monotonic()
            if gap > 0:
                await asyncio.sleep(gap)

            try:
                resp = await self._http.get(url)
                _last_request_time = time.monotonic()

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code in (429, 500, 502, 503, 504):
                    if server_attempts < len(_BACKOFF):
                        await asyncio.sleep(_BACKOFF[server_attempts])
                        server_attempts += 1
                        continue
                    return None  # exhausted server-error retries

                # Non-retryable 4xx
                return None

            except httpx.TransportError as exc:
                # Network/connectivity issue — retry indefinitely until back online
                _last_request_time = time.monotonic()
                print(f"\n[connectivity] {exc!r} — retrying in {_CONNECTIVITY_RETRY}s", file=sys.stderr, flush=True)
                await asyncio.sleep(_CONNECTIVITY_RETRY)

            except httpx.RequestError:
                # Protocol-level error — counts against server-error budget
                _last_request_time = time.monotonic()
                if server_attempts < len(_BACKOFF):
                    await asyncio.sleep(_BACKOFF[server_attempts])
                    server_attempts += 1
                    continue
                return None

    async def get_poets(self) -> list[dict] | None:
        return await self._get("/api/ganjoor/poets")

    async def get_poet(self, poet_id: int) -> dict | None:
        return await self._get(f"/api/ganjoor/poet/{poet_id}")

    async def get_category(self, cat_id: int) -> dict | None:
        return await self._get(f"/api/ganjoor/cat/{cat_id}?poems=true&cat=true")

    async def get_poem(self, poem_id: int) -> dict | None:
        return await self._get(f"/api/ganjoor/poem/{poem_id}?verses=true")
