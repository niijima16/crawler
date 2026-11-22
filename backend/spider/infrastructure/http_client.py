import httpx

from spider.application.ports import LoginFailed, UpstreamError

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

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, url: str, data: dict[str, str] | None = None) -> str:
        try:
            response = await self._http.request(method, url, data=data)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError from exc
        return response.text
