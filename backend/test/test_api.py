import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from spider.application.favorites import FavoriteDeps
from spider.application.ports import LoginFailed, UpstreamError
from spider.application.preview import CheckoutParsers, PreviewConfig
from spider.application.retry import PreviewRuntime
from spider.application.use_cases import SALES_HISTORY_URL, ProductNotFound
from spider.domain.account import Account
from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.product_parser import extract_latest_product_name
from spider.infrastructure.product_parsers import (
    extract_confirm,
    extract_order_form,
    extract_payment_options,
    extract_product_ids,
    extract_product_page,
    extract_search_results,
    is_in_cart,
    is_recaptcha_rejected,
)
from spider.infrastructure.secret_box import FernetSecretBox
from spider.presentation.api import LIST_URL, Dependencies, create_app
from test.fake_repos import MemoryRepos
from test.fakes import (
    CONFIRM_URL,
    PID,
    PRODUCT_URL,
    SHIPPING_URL,
    FakeSite,
    FakeTime,
    html,
)

BODY = {"email": "a@example.test", "password": "secret-pw"}
SEARCH_ALL = "https://www.dollyteria.com/product-list?keyword=%E8%B1%86%E6%9C%AC"
SEARCH_STOCK = SEARCH_ALL + "&available=1"


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

    async def post(self, url: str, data: dict[str, str]) -> str:
        raise NotImplementedError

    def get_cookie(self, name: str) -> str | None:
        return "sess-xyz" if name == "PHPSESSID" else None

    async def aclose(self) -> None:
        self.closed = True


class Factory:
    def __init__(self, **client_kwargs: Exception | None) -> None:
        self.created: list[FakeClient] = []
        self._kwargs = client_kwargs

    def __call__(self) -> FakeClient:
        pages = {
            LIST_URL: html("product_list_new.html"),
            SALES_HISTORY_URL: html("sales_history.html"),
            f"https://www.dollyteria.com/product/{810297}": html("product_page_purchasable.html"),
            SEARCH_ALL: html("product_list_keyword.html"),
            SEARCH_STOCK: html("product_list_keyword_available.html"),
        }
        client = FakeClient(pages, **self._kwargs)
        self.created.append(client)
        return client


def _deps(
    factory: Any,
    *,
    allow_order_submit: bool = False,
    parallelism: int = 1,
    repos: MemoryRepos | None = None,
) -> Dependencies:
    clock = FakeTime()
    return Dependencies(
        client_factory=factory,
        extract_latest_name=extract_latest_product_name,
        extract_orders=extract_orders,
        extract_product_page=extract_product_page,
        extract_search_results=extract_search_results,
        extract_product_ids=extract_product_ids,
        checkout_parsers=CheckoutParsers(
            is_in_cart=is_in_cart,
            payment_options=extract_payment_options,
            confirm=extract_confirm,
            order_form=extract_order_form,
            recaptcha_rejected=is_recaptcha_rejected,
            order_ids=lambda page: {o.order_id for o in extract_orders(page)},
        ),
        preview_config=PreviewConfig(
            parallelism=parallelism,
            deadline_seconds=30.0,
            history_deadline_seconds=10.0,
            allow_order_submit=allow_order_submit,
        ),
        runtime=PreviewRuntime(sleep=clock.sleep, rng=lambda: 1.0, now=clock),
        login_deadline_seconds=15.0,
        favorite_deps=_favorite_deps(factory, clock, repos or MemoryRepos()),
        on_startup=_noop,
    )


async def _noop() -> None:
    return None


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 11, 22, 11, 0, tzinfo=UTC)  # JST 20:00


def _favorite_deps(factory: Any, clock: FakeTime, repos: MemoryRepos) -> FavoriteDeps:
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"id{counter['n']}"

    return FavoriteDeps(
        accounts=repos.accounts,
        favorites=repos.favorites,
        notifications=repos.notifications,
        settings=repos.settings,
        secret_box=FernetSecretBox(Fernet.generate_key().decode()),
        clock=_FixedClock(),
        new_id=new_id,
        client_factory=factory,
        extract_product_page=extract_product_page,
        runtime=PreviewRuntime(sleep=clock.sleep, rng=lambda: 1.0, now=clock),
        login_deadline_seconds=15.0,
    )


def _app(factory: Any, **kwargs: Any) -> TestClient:
    return TestClient(create_app(_deps(factory, **kwargs)))


# --- 既存の API（/api 配下） ---------------------------------------------------


def test_latest_product_returns_name() -> None:
    with _app(Factory()) as client:
        response = client.get("/api/latest-product")

    assert response.status_code == 200
    assert response.json() == {"name": "MSD/健 I-26-11-19-382-KD-ZI"}


def test_purchase_history_returns_orders() -> None:
    with _app(Factory()) as client:
        response = client.post("/api/purchase-history", json=BODY)

    assert response.status_code == 200
    assert response.json()[0] == {
        "order_id": "96235",
        "purchased_on": "2026-10-21",
        "total_yen": 2860,
    }
    assert len(response.json()) == 3


def test_missing_field_is_422_without_echoing_password() -> None:
    with _app(Factory()) as client:
        response = client.post("/api/purchase-history", json={"password": "secret-pw"})

    assert response.status_code == 422
    assert "secret-pw" not in response.text


def test_login_failure_is_401_without_credentials_in_body() -> None:
    with _app(Factory(login_error=LoginFailed())) as client:
        response = client.post("/api/purchase-history", json=BODY)

    assert response.status_code == 401
    assert "secret-pw" not in response.text
    assert "a@example.test" not in response.text


def test_upstream_error_is_502() -> None:
    with _app(Factory(get_error=UpstreamError())) as client:
        response = client.get("/api/latest-product")

    assert response.status_code == 502


def test_latest_product_not_found_is_502() -> None:
    deps = _deps(Factory())._replace(
        extract_latest_name=lambda page: extract_latest_product_name("<html/>")
    )

    with TestClient(create_app(deps)) as client:
        response = client.get("/api/latest-product")

    assert response.status_code == 502


def test_latest_product_reuses_one_shared_client() -> None:
    factory = Factory()

    with _app(factory) as client:
        client.get("/api/latest-product")
        client.get("/api/latest-product")
        assert len(factory.created) == 1
        assert not factory.created[0].closed

    assert factory.created[0].closed


def test_purchase_history_uses_and_closes_a_new_client_per_request() -> None:
    factory = Factory()

    with _app(factory) as client:
        client.post("/api/purchase-history", json=BODY)
        client.post("/api/purchase-history", json=BODY)

        shared, first, second = factory.created
        assert not shared.closed
        assert first.closed and second.closed


def test_healthz_returns_ok() -> None:
    with _app(Factory()) as client:
        response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_old_unprefixed_paths_are_gone() -> None:
    with _app(Factory()) as client:
        assert client.get("/latest-product").status_code == 404


# --- 商品検索・支払方法 -------------------------------------------------------


def test_product_by_id() -> None:
    with _app(Factory()) as client:
        response = client.get("/api/products/810297")

    assert response.status_code == 200
    assert response.json() == {
        "product_id": 810297,
        "name": "SD/豆本 I-26-11-05-335-KD-ZI",
        "price_yen": 550,
        "in_stock": True,
    }


def test_product_by_id_not_found_is_404() -> None:
    with _app(Factory(get_error=ProductNotFound())) as client:
        response = client.get("/api/products/1")

    assert response.status_code == 404


def test_search_by_keyword_returns_whole_names_and_stock() -> None:
    with _app(Factory()) as client:
        response = client.get("/api/products", params={"keyword": "豆本"})

    assert response.status_code == 200
    assert [(p["product_id"], p["name"], p["in_stock"]) for p in response.json()] == [
        (775386, "SD/豆本 S-26-08-09-376-TO-ZS", True),
        (810296, "SD/豆本 I-26-11-05-334-KD-ZI", False),
        (810297, "SD/豆本 I-26-11-05-335-KD-ZI", True),
    ]


def test_search_requires_a_keyword() -> None:
    with _app(Factory()) as client:
        assert client.get("/api/products").status_code == 422
        assert client.get("/api/products", params={"keyword": ""}).status_code == 422


def test_search_upstream_error_is_502() -> None:
    with _app(Factory(get_error=UpstreamError())) as client:
        response = client.get("/api/products", params={"keyword": "豆本"})

    assert response.status_code == 502


def test_payment_methods_lists_all_eight() -> None:
    with _app(Factory()) as client:
        response = client.get("/api/payment-methods")

    methods = {m["id"]: m for m in response.json()}
    assert len(methods) == 8
    assert methods["8"]["label"] == "店頭支払"
    assert methods["10000028"]["preview_supported"] is False
    assert methods["10000006"]["submit_supported"] is False


# --- ログイン確認 -------------------------------------------------------------


def test_login_check_succeeds_without_returning_any_session() -> None:
    factory = Factory()

    with _app(factory) as client:
        response = client.post("/api/login-check", json=BODY)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "secret-pw" not in response.text
    assert factory.created[-1].closed


def test_login_check_failure_is_401() -> None:
    with _app(Factory(login_error=LoginFailed())) as client:
        response = client.post("/api/login-check", json=BODY)

    assert response.status_code == 401
    assert "secret-pw" not in response.text


def test_login_check_gives_up_with_504_when_the_site_stays_down() -> None:
    with _app(Factory(login_error=UpstreamError())) as client:
        response = client.post("/api/login-check", json=BODY)

    assert response.status_code == 504


# --- 確認画面までの進行 -------------------------------------------------------

PREVIEW = {**BODY, "product_id": PID}


def test_store_pickup_preview_returns_the_confirmation_summary() -> None:
    with _app(FakeSite().factory) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.status_code == 200
    assert response.json() == {
        "preview": {
            "product_id": PID,
            "item_name": "SD16/OF:靴 U-26-07-22-192-TN-ZU",
            "payment_method": "店頭支払",
            "shipping_fee_yen": 660,
            "total_yen": 3740,
        },
        "attempts": 4,
        "order": None,
        "handoff": None,
    }
    assert "secret-pw" not in response.text


def test_store_pickup_preview_with_another_payment_method() -> None:
    site = FakeSite(confirm_label="代金引換")

    with _app(site.factory) as client:
        response = client.post("/api/store-pickup-preview", json={**PREVIEW, "payment_method": "3"})

    assert response.status_code == 200
    assert response.json()["preview"]["payment_method"] == "代金引換"


def test_store_pickup_preview_login_failure_is_401() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "LOGIN":
            raise LoginFailed

    with _app(FakeSite(hook=hook).factory) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.status_code == 401
    assert "secret-pw" not in response.text


def test_store_pickup_preview_product_not_found_is_404() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "POST" and url == PRODUCT_URL:
            raise ProductNotFound

    with _app(FakeSite(hook=hook).factory) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.status_code == 404


def test_store_pickup_preview_sold_out_is_409() -> None:
    with _app(FakeSite(cart="product_page_soldout.html").factory) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.status_code == 409
    assert response.json()["detail"] == "not_purchasable"


def test_store_pickup_preview_payment_method_unavailable_is_409() -> None:
    with _app(FakeSite(shipping="cart_shipping_no_pickup.html").factory) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.status_code == 409
    assert response.json()["detail"] == "payment_method_unavailable"


def test_store_pickup_preview_unsupported_payment_method_is_422_without_requests() -> None:
    site = FakeSite()

    with _app(site.factory) as client:
        card = client.post(
            "/api/store-pickup-preview", json={**PREVIEW, "payment_method": "10000028"}
        )
        unknown = client.post(
            "/api/store-pickup-preview", json={**PREVIEW, "payment_method": "999"}
        )

    assert card.status_code == 422 and unknown.status_code == 422
    assert card.json()["detail"] == "unsupported_payment_method:preview"
    assert unknown.json()["detail"] == "unsupported_payment_method:unknown"
    assert len(site.clients) == 1  # 共有クライアントだけ（起動時）。ログインは一切していない
    assert site.log == []


def test_store_pickup_preview_missing_fields_is_422_without_echoing_password() -> None:
    with _app(FakeSite().factory) as client:
        response = client.post("/api/store-pickup-preview", json={"password": "secret-pw"})

    assert response.status_code == 422
    assert "secret-pw" not in response.text


def test_store_pickup_preview_times_out_with_504() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "LOGIN":
            raise UpstreamError

    with _app(FakeSite(hook=hook).factory) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.status_code == 504


def test_order_submission_is_forbidden_unless_enabled_on_the_server() -> None:
    site = FakeSite()

    with _app(site.factory, allow_order_submit=False) as client:
        response = client.post("/api/store-pickup-preview", json={**PREVIEW, "submit_order": True})

    assert response.status_code == 403
    assert site.log == []


def test_order_submission_defaults_to_false() -> None:
    site = FakeSite()

    with _app(site.factory, allow_order_submit=True) as client:
        response = client.post("/api/store-pickup-preview", json=PREVIEW)

    assert response.json()["order"] is None
    assert site.requests("POST", CONFIRM_URL) == []
    assert site.requests("POST", SHIPPING_URL) != []


def test_order_submission_when_enabled_and_requested() -> None:
    site = FakeSite()

    with _app(site.factory, allow_order_submit=True) as client:
        response = client.post("/api/store-pickup-preview", json={**PREVIEW, "submit_order": True})

    assert response.status_code == 200
    assert response.json()["order"] == {"status": "submitted", "order_id": "96301", "reason": None}


# --- アカウント・お気に入り・通知・自動購入 -------------------------------------------

ACCOUNT = {"label": "テスト用 A", **BODY}
PRODUCT = 810297


def _with_account(client: TestClient) -> str:
    response = client.post("/api/accounts", json=ACCOUNT)
    assert response.status_code == 200
    account_id: str = response.json()["id"]
    return account_id


def test_register_and_list_accounts_never_expose_the_password() -> None:
    with _app(Factory()) as client:
        created = client.post("/api/accounts", json=ACCOUNT)
        listed = client.get("/api/accounts")

    assert created.status_code == 200
    assert created.json() == {"id": "id1", "label": "テスト用 A", "email": "a@example.test"}
    assert listed.json() == [created.json()]
    assert "secret-pw" not in created.text + listed.text


def test_register_account_with_a_wrong_password_is_401_and_stores_nothing() -> None:
    with _app(Factory(login_error=LoginFailed())) as client:
        response = client.post("/api/accounts", json=ACCOUNT)
        listed = client.get("/api/accounts")

    assert response.status_code == 401
    assert "secret-pw" not in response.text
    assert listed.json() == []


def test_registering_the_same_email_twice_is_409() -> None:
    with _app(Factory()) as client:
        _with_account(client)
        response = client.post("/api/accounts", json=ACCOUNT)

    assert response.status_code == 409
    assert response.json()["detail"] == "duplicate_account"


def test_delete_account() -> None:
    with _app(Factory()) as client:
        account_id = _with_account(client)

        assert client.delete(f"/api/accounts/{account_id}").status_code == 204
        assert client.delete(f"/api/accounts/{account_id}").status_code == 404


def test_add_list_update_and_delete_a_favorite() -> None:
    with _app(Factory()) as client:
        account_id = _with_account(client)

        added = client.post(
            "/api/favorites",
            json={"account_id": account_id, "product_id": PRODUCT, "price_cap_yen": 1500},
        )
        listed = client.get("/api/favorites", params={"account_id": account_id})
        patched = client.patch(
            f"/api/favorites/{added.json()['id']}",
            json={"payment_method": "3", "price_cap_yen": None},
        )
        removed = client.delete(f"/api/favorites/{added.json()['id']}")

    assert added.status_code == 200
    body = added.json()
    assert (body["product_id"], body["product_name"], body["state"], body["payment_method"]) == (
        PRODUCT,
        "SD/豆本 I-26-11-05-335-KD-ZI",
        "watching",
        "8",
    )
    assert body["price_cap_yen"] == 1500
    assert listed.json() == [body]
    assert patched.json()["payment_method"] == "3"
    assert patched.json()["price_cap_yen"] is None
    assert removed.status_code == 204


def test_favorite_errors() -> None:
    with _app(Factory()) as client:
        account_id = _with_account(client)
        base = {"account_id": account_id, "product_id": PRODUCT}

        assert client.post("/api/favorites", json={**base, "account_id": "nope"}).status_code == 404
        unsupported = client.post("/api/favorites", json={**base, "payment_method": "10000006"})
        assert unsupported.status_code == 422
        assert unsupported.json()["detail"] == "unsupported_payment_method:submit"
        assert client.post("/api/favorites", json=base).status_code == 200
        duplicate = client.post("/api/favorites", json=base)
        assert (duplicate.status_code, duplicate.json()["detail"]) == (409, "duplicate_favorite")
        assert client.post("/api/favorites", json={"account_id": account_id}).status_code == 422
        assert client.patch("/api/favorites/missing", json={}).status_code == 404
        assert client.delete("/api/favorites/missing").status_code == 404


def test_a_missing_product_cannot_be_a_favorite() -> None:
    with _app(Factory(get_error=ProductNotFound())) as client:
        account_id = _with_account(client)
        response = client.post("/api/favorites", json={"account_id": account_id, "product_id": 1})

    assert response.status_code == 404


def test_resuming_a_favorite_that_is_being_purchased_is_409() -> None:
    repos = MemoryRepos()

    with TestClient(create_app(_deps(Factory(), repos=repos))) as client:
        account_id = _with_account(client)
        favorite = client.post(
            "/api/favorites", json={"account_id": account_id, "product_id": PRODUCT}
        ).json()
        asyncio.run(
            repos.favorites.transition(
                favorite["id"], "watching", "purchasing", 0, datetime(2026, 11, 22, tzinfo=UTC)
            )
        )
        response = client.patch(f"/api/favorites/{favorite['id']}", json={"resume": True})

    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_transition"


def test_notifications_and_the_auto_purchase_status() -> None:
    with _app(Factory(), allow_order_submit=True) as client:
        notes = client.get("/api/notifications")
        read = client.post("/api/notifications/read")
        status = client.get("/api/auto-purchase/status")
        off = client.put("/api/auto-purchase/enabled", json={"enabled": False})

    assert notes.json() == {"unread": 0, "items": []}
    assert read.json() == {"unread": 0}
    assert status.json() == {
        "enabled": True,
        "order_submit_allowed": True,
        "last_tick_at": None,
        "next_nightly_at": "2026-11-22T21:00:00+09:00",
    }
    assert off.json()["enabled"] is False


# --- 保存済みのアカウントで実行する -------------------------------------------------


def test_preview_with_a_saved_account_uses_its_stored_credentials() -> None:
    site = FakeSite()

    with _app(site.factory) as client:
        account_id = _with_account(client)
        response = client.post(
            "/api/store-pickup-preview", json={"account_id": account_id, "product_id": PID}
        )

    assert response.status_code == 200
    assert response.json()["preview"]["item_name"] == "SD16/OF:靴 U-26-07-22-192-TN-ZU"
    logins = [d for _, m, _, d in site.log if m == "LOGIN"]
    assert logins[-1] == {"email": "a@example.test"}
    assert "secret-pw" not in response.text


def test_preview_with_an_unknown_account_is_404() -> None:
    with _app(FakeSite().factory) as client:
        response = client.post(
            "/api/store-pickup-preview", json={"account_id": "nope", "product_id": PID}
        )

    assert response.status_code == 404


def test_preview_needs_either_an_account_or_credentials() -> None:
    with _app(FakeSite().factory) as client:
        response = client.post("/api/store-pickup-preview", json={"product_id": PID})
        partial = client.post(
            "/api/store-pickup-preview", json={"product_id": PID, "email": "a@example.test"}
        )

    assert response.status_code == 422 and partial.status_code == 422


def test_preview_with_credentials_that_cannot_be_decrypted_is_401() -> None:
    repos = MemoryRepos()
    site = FakeSite()

    with TestClient(create_app(_deps(site.factory, repos=repos))) as client:
        account_id = _with_account(client)
        asyncio.run(
            repos.accounts.add(Account(id=account_id, label="x", email="a@example.test"), "garbage")
        )
        response = client.post(
            "/api/store-pickup-preview", json={"account_id": account_id, "product_id": PID}
        )

    assert response.status_code == 401


# --- 引き継ぎ（handoff） ------------------------------------------------------


def test_handoff_returns_the_session_without_logging_the_password(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _app(FakeSite().factory) as client:
        response = client.post("/api/store-pickup-preview", json={**PREVIEW, "handoff": True})

    assert response.status_code == 200
    body = response.json()
    assert body["handoff"] == {
        "cookie_name": "PHPSESSID",
        "cookie_value": "sess-xyz",
        "confirm_url": "https://www.dollyteria.com/cart/confirm",
    }
    assert body["order"] is None
    assert "secret-pw" not in response.text
    assert "secret-pw" not in capsys.readouterr().out


def test_handoff_and_submit_order_together_is_422() -> None:
    site = FakeSite()

    with _app(site.factory, allow_order_submit=True) as client:
        response = client.post(
            "/api/store-pickup-preview", json={**PREVIEW, "handoff": True, "submit_order": True}
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "handoff_and_submit"
    assert site.log == []


def test_handoff_with_the_credit_card_is_422() -> None:
    with _app(FakeSite().factory) as client:
        response = client.post(
            "/api/store-pickup-preview",
            json={**PREVIEW, "handoff": True, "payment_method": "10000028"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported_payment_method:preview"
