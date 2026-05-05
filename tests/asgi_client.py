from __future__ import annotations

import asyncio
from typing import Any

import httpx


class ASGITestClient:
    """Small synchronous test client for the installed Starlette client regression."""

    def __init__(self, app: Any, base_url: str = "http://testserver") -> None:
        self.app = app
        self.base_url = base_url
        self.cookies = httpx.Cookies()

    def __enter__(self) -> "ASGITestClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        follow_redirects = kwargs.pop("follow_redirects", True)
        return asyncio.run(self._request(method, path, follow_redirects=follow_redirects, **kwargs))

    async def _request(self, method: str, path: str, follow_redirects: bool, **kwargs: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=self.base_url,
            cookies=self.cookies,
            follow_redirects=follow_redirects,
        ) as client:
            response = await client.request(method, path, **kwargs)
            self.cookies.update(client.cookies)
            return response
