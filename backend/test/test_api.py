from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from spider.application.ports import LoginFailed, UpstreamError
from spider.application.use_cases import SALES_HISTORY_URL
from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.product_parser import extract_latest_product_name
from spider.presentation.api import LIST_URL, create_app

FIXTURES = Path(__file__).parent / "fixtures"
BODY = {"email": "a@example.test", "password": "secret-pw"}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeClient:
    def __init__(
        self,
        pages: Mapping[str, str],
        *,
        login_error: Exception | None = None,
        get_error: Exception | None = None,
    ) -> None:
        self._pages = pages
        self._login_error = login_error
        self._get_error = get_error
        self.closed = False

    async def login(self, email: str, password: str) -> None:
        if self._login_error:
            raise self._login_error

    async def get(self, url: str) -> str:
        if self._get_error:
            raise self._get_error
        return self._pages[url]

    async def aclose(self) -> None:
        self.closed = True


class Factory:
    def __init__(self, **client_kwargs: Exception | None) -> None:
        self.created: list[FakeClient] = []
        self._kwargs = client_kwargs

    def __call__(self) -> FakeClient:
        pages = {
            LIST_URL: _fixture("product_list_new.html"),
            SALES_HISTORY_URL: _fixture("sales_history.html"),
        }
        client = FakeClient(pages, **self._kwargs)
        self.created.append(client)
        return client


def _app(factory: Factory) -> TestClient:
    return TestClient(create_app(factory, extract_latest_product_name, extract_orders))


def test_latest_product_returns_name() -> None:
    with _app(Factory()) as client:
        response = client.get("/latest-product")

    assert response.status_code == 200
    assert response.json() == {"name": "MSD/健 I-26-11-19-382-KD-ZI"}


def test_purchase_history_returns_orders() -> None:
    with _app(Factory()) as client:
        response = client.post("/purchase-history", json=BODY)

    assert response.status_code == 200
    assert response.json()[0] == {
        "order_id": "96235",
        "purchased_on": "2026-10-21",
        "total_yen": 2860,
    }
    assert len(response.json()) == 3


def test_missing_field_is_422_without_echoing_password() -> None:
    with _app(Factory()) as client:
        response = client.post("/purchase-history", json={"password": "secret-pw"})

    assert response.status_code == 422
    assert "secret-pw" not in response.text


def test_login_failure_is_401_without_credentials_in_body() -> None:
    with _app(Factory(login_error=LoginFailed())) as client:
        response = client.post("/purchase-history", json=BODY)

    assert response.status_code == 401
    assert "secret-pw" not in response.text
    assert "a@example.test" not in response.text


def test_upstream_error_is_502() -> None:
    with _app(Factory(get_error=UpstreamError())) as client:
        response = client.get("/latest-product")

    assert response.status_code == 502


def test_product_not_found_is_502() -> None:
    factory = Factory()
    app = create_app(factory, lambda html: extract_latest_product_name("<html/>"), extract_orders)

    with TestClient(app) as client:
        response = client.get("/latest-product")

    assert response.status_code == 502


def test_latest_product_reuses_one_shared_client() -> None:
    factory = Factory()

    with _app(factory) as client:
        client.get("/latest-product")
        client.get("/latest-product")
        assert len(factory.created) == 1
        assert not factory.created[0].closed

    assert factory.created[0].closed


def test_purchase_history_uses_and_closes_a_new_client_per_request() -> None:
    factory = Factory()

    with _app(factory) as client:
        client.post("/purchase-history", json=BODY)
        client.post("/purchase-history", json=BODY)

        shared, first, second = factory.created
        assert not shared.closed
        assert first.closed and second.closed
