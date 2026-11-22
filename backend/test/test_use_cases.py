from datetime import date

import pytest

from spider.application.ports import LoginFailed
from spider.application.use_cases import (
    SALES_HISTORY_URL,
    get_latest_product_name,
    get_purchase_history,
)
from spider.domain.order import Order

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

    async def aclose(self) -> None:
        pass


async def test_latest_product_name_does_not_login() -> None:
    client = FakeClient()

    name = await get_latest_product_name(client, "https://example.test/list", lambda html: "NAME")

    assert name == "NAME"
    assert client.calls == [("get", "https://example.test/list")]


async def test_purchase_history_logs_in_then_fetches_history() -> None:
    client = FakeClient()
    order = Order(order_id="1", purchased_on=date(2026, 1, 1), total_yen=100)

    orders = await get_purchase_history(client, "a@example.test", "pw", lambda html: [order])

    assert orders == [order]
    assert client.calls == [("login", "a@example.test"), ("get", SALES_HISTORY_URL)]


async def test_purchase_history_does_not_fetch_when_login_fails() -> None:
    client = FakeClient(login_fails=True)

    with pytest.raises(LoginFailed):
        await get_purchase_history(client, "a@example.test", "bad", lambda html: [])

    assert client.calls == [("login", "a@example.test")]
