from collections.abc import Callable

import pytest

from spider.application.ports import UpstreamError
from spider.domain.keyword_favorite import GENRES, Genre
from spider.infrastructure.category_provider import SiteCategoryProvider

pytestmark = pytest.mark.anyio

SAMPLE = [Genre(category_id=22, label="A > 本体"), Genre(category_id=24, label="A > ウィッグ")]


class FakeClient:
    def __init__(self, pages: dict[str, str], error: Exception | None = None) -> None:
        self._pages = pages
        self._error = error
        self.gets: list[str] = []
        self.closed = 0

    async def login(self, email: str, password: str) -> None: ...

    async def get(self, url: str) -> str:
        self.gets.append(url)
        if self._error is not None:
            raise self._error
        return self._pages.get(url, "")

    async def post(self, url: str, data: dict[str, str]) -> str:
        return ""

    def get_cookie(self, name: str) -> str | None:
        return None

    async def aclose(self) -> None:
        self.closed += 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _provider(
    client: FakeClient,
    clock: FakeClock,
    *,
    parse: Callable[[str], list[Genre]] = lambda _html: SAMPLE,
    ttl: float = 100.0,
) -> SiteCategoryProvider:
    return SiteCategoryProvider(
        client_factory=lambda: client, parse=parse, now=clock, ttl_seconds=ttl
    )


async def test_fetches_once_then_serves_from_cache_within_ttl() -> None:
    client = FakeClient({"https://www.example.com/product-list/22": "<html>ok</html>"})
    clock = FakeClock()
    provider = _provider(client, clock)

    first = await provider.list_categories()
    clock.now += 50  # TTL(100)内
    second = await provider.list_categories()

    assert first == SAMPLE
    assert second == SAMPLE
    assert len(client.gets) == 1  # 2回目は取りに行かない


async def test_refetches_after_ttl_expires() -> None:
    client = FakeClient({"https://www.example.com/product-list/22": "<html>ok</html>"})
    clock = FakeClock()
    provider = _provider(client, clock)

    await provider.list_categories()
    clock.now += 101  # TTL超過
    await provider.list_categories()

    assert len(client.gets) == 2


async def test_falls_back_to_fixed_genres_when_fetch_fails() -> None:
    client = FakeClient({}, error=UpstreamError())
    provider = _provider(client, FakeClock())

    result = await provider.list_categories()

    assert result == list(GENRES)
    assert client.closed == 1  # 失敗でもクライアントは閉じる


async def test_falls_back_when_the_page_has_no_categories() -> None:
    client = FakeClient({"https://www.example.com/product-list/22": "<html></html>"})
    provider = _provider(client, FakeClock(), parse=lambda html: [])

    result = await provider.list_categories()

    assert result == list(GENRES)
