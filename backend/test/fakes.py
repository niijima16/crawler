import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from spider.application.use_cases import SALES_HISTORY_URL

FIXTURES = Path(__file__).parent / "fixtures"
SITE = "https://www.dollyteria.com"
PID = 769926
PRODUCT_URL = f"{SITE}/product/{PID}"
CUSTOMER_URL = f"{SITE}/cart/customer"
SHIPPING_URL = f"{SITE}/cart/shipping"
CONFIRM_URL = f"{SITE}/cart/confirm"

Hook = Callable[[int, str, str], Awaitable[None]]


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


class FakeSite:
    """サイトの代わり。リクエストを記録し、固定のページを返す。"""

    def __init__(
        self,
        *,
        confirm_label: str = "店頭支払",
        shipping: str = "cart_shipping.html",
        cart: str = "cart_with_item.html",
        accept_order: bool = True,
        order_response: str = "cart_confirm.html",
        product_page: str | None = None,
        other_product_page: str | None = None,
        hook: Hook | None = None,
    ) -> None:
        self.log: list[tuple[int, str, str, dict[str, str] | None]] = []
        self.cookies: dict[str, str] = {"PHPSESSID": "sess-xyz"}
        self.clients: list[FakeClient] = []
        self.order_posts = 0
        self._confirm = html("cart_confirm.html").replace("店頭支払", confirm_label)
        self._shipping = html(shipping)
        self._cart = html(cart)
        self._order_response = html(order_response)
        self._accept = accept_order
        self._product_page = product_page
        self._other_product_page = other_product_page
        self._history_before = html("sales_history.html")
        self._history_after = self._history_before.replace("96235", "96301", 1)
        self.hook = hook

    def factory(self) -> "FakeClient":
        client = FakeClient(self, len(self.clients))
        self.clients.append(client)
        return client

    def history(self) -> str:
        return self._history_after if self.order_posts and self._accept else self._history_before

    def page(self, method: str, url: str) -> str:
        if method == "GET" and url == CUSTOMER_URL:
            return self._shipping
        if method == "GET" and url == SALES_HISTORY_URL:
            return self.history()
        if method == "GET" and url == PRODUCT_URL and self._product_page is not None:
            return self._product_page
        if method == "GET" and url.startswith(f"{SITE}/product/") and self._other_product_page:
            return self._other_product_page
        if method == "POST" and url == PRODUCT_URL:
            return self._cart
        if method == "POST" and url == SHIPPING_URL:
            return self._confirm
        if method == "POST" and url == CONFIRM_URL:
            self.order_posts += 1
            return self._order_response
        raise AssertionError(f"unexpected {method} {url}")

    def requests(self, method: str, url: str) -> list[dict[str, str] | None]:
        return [d for _, m, u, d in self.log if m == method and u == url]


class FakeClient:
    def __init__(self, site: FakeSite, index: int) -> None:
        self._site = site
        self.index = index
        self.closed = False

    async def _enter(self, method: str, url: str, data: dict[str, str] | None) -> None:
        self._site.log.append((self.index, method, url, data))
        if self._site.hook is not None:
            await self._site.hook(self.index, method, url)

    async def login(self, email: str, password: str) -> None:
        await self._enter("LOGIN", "login", {"email": email})

    async def get(self, url: str) -> str:
        await self._enter("GET", url, None)
        return self._site.page("GET", url)

    async def post(self, url: str, data: dict[str, str]) -> str:
        await self._enter("POST", url, data)
        return self._site.page("POST", url)

    def get_cookie(self, name: str) -> str | None:
        return self._site.cookies.get(name)

    async def aclose(self) -> None:
        self.closed = True
