from typing import Protocol


class LoginFailed(Exception):
    """ログインに失敗した。"""


class UpstreamError(Exception):
    """上流サイトへのリクエストが失敗した（接続エラー・5xx など）。"""


class SiteClient(Protocol):
    async def login(self, email: str, password: str) -> None: ...

    async def get(self, url: str) -> str: ...

    async def aclose(self) -> None: ...
