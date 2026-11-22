from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from spider.application.ports import LoginFailed, UpstreamError
from spider.application.use_cases import ProductNotFound
from spider.infrastructure.http_client import LOGIN_URL, HttpSiteClient

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


async def test_login_posts_expected_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_fixture("login_success.html"))

    await HttpSiteClient(httpx.MockTransport(handler)).login("a@example.test", "pw")

    assert str(seen[0].url) == LOGIN_URL
    assert seen[0].method == "POST"
    assert parse_qs(seen[0].content.decode()) == {
        "mode": ["memberlogin"],
        "email": ["a@example.test"],
        "password": ["pw"],
        "go-login": ["ログイン"],
    }


async def test_login_fails_without_logout_link() -> None:
    client = HttpSiteClient(
        httpx.MockTransport(lambda r: httpx.Response(200, text=_fixture("login_failure.html")))
    )

    with pytest.raises(LoginFailed):
        await client.login("a@example.test", "bad")


async def test_session_cookie_is_sent_on_later_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                text=_fixture("login_success.html"),
                headers={"Set-Cookie": "PHPSESSID=abc; Path=/"},
            )
        return httpx.Response(200, text=request.headers.get("cookie", ""))

    client = HttpSiteClient(httpx.MockTransport(handler))
    await client.login("a@example.test", "pw")

    assert await client.get("https://www.dollyteria.com/sales-history") == "PHPSESSID=abc"


async def test_server_error_becomes_upstream_error() -> None:
    client = HttpSiteClient(httpx.MockTransport(lambda r: httpx.Response(503)))

    with pytest.raises(UpstreamError):
        await client.get("https://www.dollyteria.com/")


async def test_connection_error_becomes_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = HttpSiteClient(httpx.MockTransport(handler))

    with pytest.raises(UpstreamError):
        await client.login("a@example.test", "pw")


async def test_aclose_can_be_awaited() -> None:
    await HttpSiteClient(httpx.MockTransport(lambda r: httpx.Response(200))).aclose()


async def test_post_sends_form_data_and_returns_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="done")

    client = HttpSiteClient(httpx.MockTransport(handler))

    assert (
        await client.post("https://www.dollyteria.com/cart/shipping", {"a": "1", "b": "ログイン"})
        == "done"
    )
    assert seen[0].method == "POST"
    assert parse_qs(seen[0].content.decode()) == {"a": ["1"], "b": ["ログイン"]}


async def test_not_found_becomes_product_not_found() -> None:
    client = HttpSiteClient(httpx.MockTransport(lambda r: httpx.Response(404)))

    with pytest.raises(ProductNotFound):
        await client.get("https://www.dollyteria.com/product/99999999")


async def test_post_server_error_becomes_upstream_error() -> None:
    client = HttpSiteClient(httpx.MockTransport(lambda r: httpx.Response(503)))

    with pytest.raises(UpstreamError):
        await client.post("https://www.dollyteria.com/cart/shipping", {})


async def test_not_found_outside_product_pages_is_an_upstream_error() -> None:
    client = HttpSiteClient(httpx.MockTransport(lambda r: httpx.Response(404)))

    with pytest.raises(UpstreamError):
        await client.get("https://www.dollyteria.com/cart/customer")
    with pytest.raises(UpstreamError):
        await client.post("https://www.dollyteria.com/cart/shipping", {})
    with pytest.raises(UpstreamError):
        await client.get("https://www.dollyteria.com/sales-history")


async def test_adding_a_missing_product_to_the_cart_is_product_not_found() -> None:
    client = HttpSiteClient(httpx.MockTransport(lambda r: httpx.Response(404)))

    with pytest.raises(ProductNotFound):
        await client.post("https://www.dollyteria.com/product/99999999", {"cart_add_1": "t"})
