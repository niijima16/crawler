from urllib.parse import urlparse

import httpx

from spider.application.ports import LoginFailed, UpstreamError
from spider.application.use_cases import ProductNotFound

LOGIN_URL = "https://www.dollyteria.com/member-login"
_LOGGED_IN_MARKER = "ログアウト"


class HttpSiteClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._http = httpx.AsyncClient(follow_redirects=True, timeout=10, transport=transport)

    async def login(self, email: str, password: str) -> None:
        text = await self._request(
            "POST",
            LOGIN_URL,
            data={
                "mode": "memberlogin",
                "email": email,
                "password": password,
                "go-login": "ログイン",
            },
        )
        if _LOGGED_IN_MARKER not in text:
            raise LoginFailed

    async def get(self, url: str) -> str:
        return await self._request("GET", url)

    async def post(self, url: str, data: dict[str, str]) -> str:
        return await self._request("POST", url, data=data)

    def get_cookie(self, name: str) -> str | None:
        return self._http.cookies.get(name)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, url: str, data: dict[str, str] | None = None) -> str:
        try:
            response = await self._http.request(method, url, data=data)
            if response.status_code == 404 and urlparse(url).path.startswith("/product/"):
                raise ProductNotFound
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError from exc
        return response.text
