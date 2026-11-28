from datetime import date

import pytest

from spider.application.login import check_login
from spider.application.ports import LoginFailed, PreviewTimeout, UpstreamError
from spider.application.products import get_product, search_products
from spider.application.retry import PreviewRuntime
from spider.application.use_cases import (
    SALES_HISTORY_URL,
    get_latest_product_name,
    get_purchase_history,
)
from spider.domain.order import Order
from spider.domain.product import ProductSummary
from test.fakes import FakeTime

pytestmark = pytest.mark.anyio


class FakeClient:
    def __init__(self, *, login_fails: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._login_fails = login_fails

    async def login(self, email: str, password: str) -> None:
        self.calls.append(("login", email))
        if self._login_fails:
            raise LoginFailed

    async def get(self, url: str) -> str:
        self.calls.append(("get", url))
        return "<html/>"

    async def post(self, url: str, data: dict[str, str]) -> str:
        raise NotImplementedError

    def get_cookie(self, name: str) -> str | None:
        return None

    async def aclose(self) -> None:
        pass


async def test_latest_product_name_does_not_login() -> None:
    client = FakeClient()

    name = await get_latest_product_name(
        client, "https://dollyteria.test/list", lambda html: "NAME"
    )

    assert name == "NAME"
    assert client.calls == [("get", "https://dollyteria.test/list")]


async def test_purchase_history_logs_in_then_fetches_history() -> None:
    client = FakeClient()
    order = Order(order_id="1", purchased_on=date(2026, 1, 1), total_yen=100)

    orders = await get_purchase_history(client, "a@dollyteria.test", "pw", lambda html: [order])

    assert orders == [order]
    assert client.calls == [("login", "a@dollyteria.test"), ("get", SALES_HISTORY_URL)]


async def test_purchase_history_does_not_fetch_when_login_fails() -> None:
    client = FakeClient(login_fails=True)

    with pytest.raises(LoginFailed):
        await get_purchase_history(client, "a@dollyteria.test", "bad", lambda html: [])

    assert client.calls == [("login", "a@dollyteria.test")]


class PagesClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.requested: list[str] = []
        self._pages = pages

    async def login(self, email: str, password: str) -> None:
        pass

    async def get(self, url: str) -> str:
        self.requested.append(url)
        return self._pages[url]

    async def post(self, url: str, data: dict[str, str]) -> str:
        raise NotImplementedError

    def get_cookie(self, name: str) -> str | None:
        return None

    async def aclose(self) -> None:
        pass


async def test_get_product_fetches_the_product_page() -> None:
    client = PagesClient({"https://www.dollyteria.com/product/815572": "<page/>"})
    summary = ProductSummary(product_id=815572, name="n", price_yen=1, in_stock=True)

    result = await get_product(client, 815572, lambda html, pid: summary)

    assert result == summary
    assert client.requested == ["https://www.dollyteria.com/product/815572"]


async def test_search_products_marks_stock_from_the_available_only_search() -> None:
    all_url = "https://www.dollyteria.com/product-list?keyword=%E8%B1%86%E6%9C%AC"
    stock_url = all_url + "&available=1"
    client = PagesClient({all_url: "ALL", stock_url: "STOCK"})
    seen: list[tuple[str, set[int]]] = []

    def results(html: str, in_stock: set[int]) -> list[ProductSummary]:
        seen.append((html, in_stock))
        return []

    await search_products(
        client, "豆本", results, lambda html: {1, 2} if html == "STOCK" else set()
    )

    assert sorted(client.requested) == sorted([all_url, stock_url])
    assert seen == [("ALL", {1, 2})]


async def test_search_products_within_a_category() -> None:
    all_url = "https://www.dollyteria.com/product-list/22?keyword=%E8%B1%86%E6%9C%AC"
    stock_url = all_url + "&available=1"
    client = PagesClient({all_url: "ALL", stock_url: "STOCK"})

    await search_products(client, "豆本", lambda html, ids: [], lambda html: set(), category_id=22)

    assert sorted(client.requested) == sorted([all_url, stock_url])


def _runtime(clock: FakeTime) -> PreviewRuntime:
    return PreviewRuntime(sleep=clock.sleep, rng=lambda: 1.0, now=clock)


class LoginClient(PagesClient):
    def __init__(self, errors: list[Exception]) -> None:
        super().__init__({})
        self.errors = errors
        self.attempts = 0

    async def login(self, email: str, password: str) -> None:
        self.attempts += 1
        if self.errors:
            raise self.errors.pop(0)


async def test_check_login_retries_transient_errors() -> None:
    client = LoginClient([UpstreamError(), UpstreamError()])

    await check_login(
        client, "a@dollyteria.test", "pw", runtime=_runtime(FakeTime()), deadline_seconds=15
    )

    assert client.attempts == 3


async def test_check_login_does_not_retry_a_failed_login() -> None:
    client = LoginClient([LoginFailed()])

    with pytest.raises(LoginFailed):
        await check_login(
            client, "a@dollyteria.test", "bad", runtime=_runtime(FakeTime()), deadline_seconds=15
        )

    assert client.attempts == 1


async def test_check_login_gives_up_at_the_deadline() -> None:
    client = LoginClient([UpstreamError()] * 100)

    with pytest.raises(PreviewTimeout):
        await check_login(
            client, "a@dollyteria.test", "pw", runtime=_runtime(FakeTime()), deadline_seconds=5
        )
