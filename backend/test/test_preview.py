import asyncio
from collections.abc import Callable

import pytest

from spider.application.ports import (
    HandoffAndSubmit,
    LoginFailed,
    NotPurchasable,
    OrderSubmitDisabled,
    PaymentMethodUnavailable,
    PreviewTimeout,
    UnsupportedPaymentMethod,
    UpstreamError,
)
from spider.application.preview import (
    CheckoutParsers,
    PreviewConfig,
    store_pickup_preview,
)
from spider.application.retry import PreviewRuntime, backoff_delay, fixed_delay
from spider.application.use_cases import SALES_HISTORY_URL, ProductNotFound
from spider.domain.product import Handoff, OrderResult, PreviewStep, StorePickupResult
from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.product_parsers import (
    extract_confirm,
    extract_order_form,
    extract_payment_options,
    is_in_cart,
    is_recaptcha_rejected,
)
from test.fakes import (
    CONFIRM_URL,
    CUSTOMER_URL,
    PID,
    PRODUCT_URL,
    SHIPPING_URL,
    FakeSite,
    FakeTime,
)

pytestmark = pytest.mark.anyio


PARSERS = CheckoutParsers(
    is_in_cart=is_in_cart,
    payment_options=extract_payment_options,
    confirm=extract_confirm,
    order_form=extract_order_form,
    recaptcha_rejected=is_recaptcha_rejected,
    order_ids=lambda html: {o.order_id for o in extract_orders(html)},
)


async def _run(
    site: FakeSite,
    *,
    parallelism: int = 1,
    submit_order: bool = False,
    allow_order_submit: bool = True,
    payment_method_id: str = "8",
    deadline_seconds: float = 60.0,
    clock: FakeTime | None = None,
    retry_delay: Callable[[int, Callable[[], float]], float] | None = None,
    handoff: bool = False,
    on_step: Callable[[PreviewStep], None] | None = None,
) -> StorePickupResult:
    clock = clock or FakeTime()
    return await store_pickup_preview(
        client_factory=site.factory,
        parsers=PARSERS,
        config=PreviewConfig(
            parallelism=parallelism,
            deadline_seconds=deadline_seconds,
            history_deadline_seconds=10.0,
            allow_order_submit=allow_order_submit,
        ),
        runtime=PreviewRuntime(sleep=clock.sleep, rng=lambda: 1.0, now=clock),
        email="a@example.test",
        password="secret-pw",
        product_id=PID,
        payment_method_id=payment_method_id,
        submit_order=submit_order,
        retry_delay=retry_delay if retry_delay is not None else backoff_delay,
        handoff=handoff,
        on_step=on_step,
    )


# --- 進行の順序とペイロード -------------------------------------------------


async def test_flow_runs_login_cart_shipping_confirm_in_order() -> None:
    site = FakeSite()

    result = await _run(site)

    assert [(m, u) for _, m, u, _ in site.log] == [
        ("LOGIN", "login"),
        ("POST", PRODUCT_URL),
        ("GET", CUSTOMER_URL),
        ("POST", SHIPPING_URL),
    ]
    assert site.requests("POST", PRODUCT_URL) == [
        {
            f"cart_add_{PID}": "t",
            "cart_operation_page": "product",
            f"cart_addquantity_{PID}": "1",
            "cart_add_btn": "カートに入れる",
        }
    ]
    shipping = site.requests("POST", SHIPPING_URL)[0]
    assert shipping is not None
    assert shipping["pay_procedure"] == "8"
    assert shipping["go-next"] == "次へ"
    assert result.preview.item_name == "SD16/OF:靴 U-26-07-22-192-TN-ZU"
    assert result.preview.total_yen == 3740
    assert result.attempts == 4
    assert result.order is None


@pytest.mark.parametrize(
    ("method_id", "label"),
    [
        ("8", "店頭支払"),
        ("3", "代金引換"),
        ("1", "銀行振込"),
        ("2", "郵便振替"),
        ("10000006", "PayPal"),
        ("10000050", "PayPayオンライン(SBペイメントサービス)"),
        ("10000002_1", "後払い(NP後払い)"),
    ],
)
async def test_selected_payment_method_is_sent(method_id: str, label: str) -> None:
    site = FakeSite(confirm_label=label)

    await _run(site, payment_method_id=method_id)

    shipping = site.requests("POST", SHIPPING_URL)[0]
    assert shipping is not None and shipping["pay_procedure"] == method_id


async def test_confirm_page_with_a_different_payment_method_is_rejected() -> None:
    site = FakeSite(confirm_label="代金引換")

    with pytest.raises(PaymentMethodUnavailable):
        await _run(site, payment_method_id="8")


async def test_payment_method_missing_on_the_shipping_page() -> None:
    site = FakeSite(shipping="cart_shipping_no_pickup.html")

    with pytest.raises(PaymentMethodUnavailable):
        await _run(site)

    assert site.requests("POST", SHIPPING_URL) == []


async def test_sold_out_product_is_not_purchasable() -> None:
    site = FakeSite(cart="product_page_soldout.html")

    with pytest.raises(NotPurchasable):
        await _run(site)


async def test_product_not_found_stops_everything() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "POST" and url == PRODUCT_URL:
            raise ProductNotFound

    site = FakeSite(hook=hook)

    with pytest.raises(ProductNotFound):
        await _run(site, parallelism=3)

    assert all(c.closed for c in site.clients)


# --- 事前検証（上流へ何も送らない） -------------------------------------------


async def test_unknown_payment_method_sends_nothing() -> None:
    site = FakeSite()

    with pytest.raises(UnsupportedPaymentMethod) as info:
        await _run(site, payment_method_id="999")

    assert info.value.reason == "unknown"
    assert site.clients == []


async def test_credit_card_is_not_supported_and_sends_nothing() -> None:
    site = FakeSite()

    with pytest.raises(UnsupportedPaymentMethod) as info:
        await _run(site, payment_method_id="10000028")

    assert info.value.reason == "preview"
    assert site.clients == []


@pytest.mark.parametrize("method_id", ["10000006", "10000050", "10000002_1"])
async def test_external_payment_methods_cannot_submit_orders(method_id: str) -> None:
    site = FakeSite()

    with pytest.raises(UnsupportedPaymentMethod) as info:
        await _run(site, payment_method_id=method_id, submit_order=True)

    assert info.value.reason == "submit"
    assert site.clients == []


async def test_order_submission_disabled_sends_nothing() -> None:
    site = FakeSite()

    with pytest.raises(OrderSubmitDisabled):
        await _run(site, submit_order=True, allow_order_submit=False)

    assert site.clients == []


# --- 競争（複数セッション） ----------------------------------------------------


async def test_first_session_to_finish_wins_and_the_rest_are_cancelled_and_closed() -> None:
    never = asyncio.Event()

    async def hook(index: int, method: str, url: str) -> None:
        if index != 0 and method == "LOGIN":
            await never.wait()

    site = FakeSite(hook=hook)

    await _run(site, parallelism=3)

    assert len(site.clients) == 3
    assert all(c.closed for c in site.clients)


async def test_a_blocked_session_does_not_prevent_others_from_getting_through() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if index == 0 and method == "LOGIN":
            raise UpstreamError

    site = FakeSite(hook=hook)

    result = await _run(site, parallelism=3)

    assert result.preview.item_name
    assert all(c.closed for c in site.clients)


async def test_login_failure_in_any_session_stops_everything() -> None:
    never = asyncio.Event()

    async def hook(index: int, method: str, url: str) -> None:
        if method == "LOGIN":
            if index == 0:
                raise LoginFailed
            await never.wait()

    site = FakeSite(hook=hook)

    with pytest.raises(LoginFailed):
        await _run(site, parallelism=3)

    assert all(c.closed for c in site.clients)


async def test_times_out_when_every_session_keeps_failing() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        raise UpstreamError

    site = FakeSite(hook=hook)

    with pytest.raises(PreviewTimeout):
        await _run(site, parallelism=2, deadline_seconds=10)

    assert all(c.closed for c in site.clients)


async def test_transient_errors_are_retried_per_step() -> None:
    failures = {"left": 2}

    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == CUSTOMER_URL and failures["left"]:
            failures["left"] -= 1
            raise UpstreamError

    site = FakeSite(hook=hook)

    result = await _run(site)

    assert [m for _, m, _, _ in site.log].count("LOGIN") == 1  # 進行状況は維持される
    assert result.attempts == 6


# --- 注文確定（オプション） ----------------------------------------------------


async def test_no_order_is_sent_unless_requested() -> None:
    site = FakeSite()

    result = await _run(site, submit_order=False)

    assert site.requests("POST", CONFIRM_URL) == []
    assert result.order is None


async def test_exactly_one_session_submits_the_order() -> None:
    site = FakeSite()

    result = await _run(site, parallelism=3, submit_order=True)

    assert site.order_posts == 1
    assert result.order == OrderResult(status="submitted", order_id="96301")
    assert all(c.closed for c in site.clients)


async def test_order_payload_has_form_fields_but_no_recaptcha_token() -> None:
    site = FakeSite()

    await _run(site, submit_order=True)

    payload = site.requests("POST", CONFIRM_URL)[0]
    assert payload == {"coupon_use": "f", "policy_agree": "1", "go-next": "購入する"}


async def test_history_is_read_before_and_after_submitting() -> None:
    site = FakeSite()

    await _run(site, submit_order=True)

    gets = [m for _, m, u, _ in site.log if m == "GET" and u == SALES_HISTORY_URL]
    assert len(gets) == 2
    order = [m for _, m, u, _ in site.log if u in (SALES_HISTORY_URL, CONFIRM_URL)]
    assert order == ["GET", "POST", "GET"]


async def test_recaptcha_rejection_without_a_new_order() -> None:
    site = FakeSite(accept_order=False, order_response="cart_confirm_recaptcha_failed.html")

    result = await _run(site, submit_order=True)

    assert result.order == OrderResult(status="rejected", reason="recaptcha")


async def test_not_accepted_without_a_new_order_or_a_known_reason() -> None:
    site = FakeSite(accept_order=False)

    result = await _run(site, submit_order=True)

    assert result.order == OrderResult(status="rejected", reason="not_accepted")


async def test_submit_failure_is_not_retried_and_is_unknown() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "POST" and url == CONFIRM_URL:
            raise UpstreamError

    site = FakeSite(accept_order=False, hook=hook)

    result = await _run(site, submit_order=True)

    assert len(site.requests("POST", CONFIRM_URL)) == 1
    assert result.order is not None
    assert result.order.status == "unknown"


async def test_submit_that_failed_but_created_an_order_is_detected() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "POST" and url == CONFIRM_URL:
            site.order_posts += 1  # サーバーでは注文が作られたが、応答が届かなかった
            raise UpstreamError

    site = FakeSite(accept_order=True, hook=hook)

    result = await _run(site, submit_order=True)

    assert result.order == OrderResult(status="submitted", order_id="96301")


async def test_order_is_not_sent_when_the_history_cannot_be_read() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == SALES_HISTORY_URL:
            raise UpstreamError

    site = FakeSite(hook=hook)

    result = await _run(site, submit_order=True)

    assert site.order_posts == 0
    assert result.order == OrderResult(status="rejected", reason="history_unavailable")


async def test_history_check_after_submitting_is_retried_but_the_order_is_not() -> None:
    state = {"gets": 0}

    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == SALES_HISTORY_URL:
            state["gets"] += 1
            if state["gets"] == 2:  # 送信後の最初の履歴取得だけ失敗
                raise UpstreamError

    site = FakeSite(hook=hook)

    result = await _run(site, submit_order=True)

    assert site.order_posts == 1
    assert result.order == OrderResult(status="submitted", order_id="96301")


# --- 引き継ぎ（handoff） ------------------------------------------------------


async def _run_handoff(site: FakeSite, **kwargs: object) -> object:
    clock = FakeTime()
    return await store_pickup_preview(
        client_factory=site.factory,
        parsers=PARSERS,
        config=PreviewConfig(
            parallelism=int(kwargs.get("parallelism", 1)),  # type: ignore[call-overload]
            deadline_seconds=60.0,
            history_deadline_seconds=10.0,
            allow_order_submit=bool(kwargs.get("allow_order_submit", False)),
        ),
        runtime=PreviewRuntime(sleep=clock.sleep, rng=lambda: 1.0, now=clock),
        email="a@example.test",
        password="secret-pw",
        product_id=PID,
        payment_method_id=str(kwargs.get("payment_method_id", "8")),
        submit_order=bool(kwargs.get("submit_order", False)),
        handoff=bool(kwargs.get("handoff", True)),
    )


async def test_handoff_reaches_the_confirmation_and_returns_the_session() -> None:
    site = FakeSite()

    result = await _run_handoff(site)

    assert result.handoff == Handoff(  # type: ignore[attr-defined]
        cookie_name="PHPSESSID",
        cookie_value="sess-xyz",
        confirm_url="https://www.dollyteria.com/cart/confirm",
    )
    assert result.order is None  # type: ignore[attr-defined]
    assert result.preview.item_name == "SD16/OF:靴 U-26-07-22-192-TN-ZU"  # type: ignore[attr-defined]
    assert site.requests("POST", CONFIRM_URL) == []  # 購入は送らない
    assert all(c.closed for c in site.clients)


async def test_handoff_without_a_session_cookie_is_an_upstream_error() -> None:
    site = FakeSite()
    site.cookies = {}

    with pytest.raises(UpstreamError):
        await _run_handoff(site)


async def test_handoff_does_not_require_order_submission_to_be_allowed() -> None:
    site = FakeSite()

    result = await _run_handoff(site, allow_order_submit=False)

    assert result.handoff is not None  # type: ignore[attr-defined]


async def test_handoff_and_submit_order_together_send_nothing() -> None:
    site = FakeSite()

    with pytest.raises(HandoffAndSubmit):
        await _run_handoff(site, submit_order=True, allow_order_submit=True)

    assert site.clients == []


async def test_handoff_rejects_the_credit_card_without_any_request() -> None:
    site = FakeSite()

    with pytest.raises(UnsupportedPaymentMethod) as info:
        await _run_handoff(site, payment_method_id="10000028")

    assert info.value.reason == "preview"
    assert site.clients == []


async def test_a_custom_retry_delay_is_used_for_every_step() -> None:
    attempts = {"n": 0}

    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == CUSTOMER_URL and attempts["n"] < 2:
            attempts["n"] += 1
            raise UpstreamError

    site = FakeSite(hook=hook)
    clock = FakeTime()

    await _run(site, clock=clock, retry_delay=fixed_delay(0.1))

    # 固定間隔なので、待ち時間は伸びず一定（rng=1.0 で 0.15）
    assert [round(s, 4) for s in clock.sleeps] == [0.15, 0.15]


async def test_the_default_retry_delay_grows_with_backoff() -> None:
    attempts = {"n": 0}

    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == CUSTOMER_URL and attempts["n"] < 2:
            attempts["n"] += 1
            raise UpstreamError

    site = FakeSite(hook=hook)
    clock = FakeTime()

    await _run(site, clock=clock)

    # 既定は指数バックオフ（rng=1.0 で 1.0, 2.0）
    assert clock.sleeps == [1.0, 2.0]


async def test_on_step_reports_each_stage_in_order_for_handoff() -> None:
    site = FakeSite()
    steps: list[tuple[str, str]] = []

    await _run(site, handoff=True, on_step=lambda s: steps.append((s.step, s.status)))

    assert steps == [
        ("login", "started"),
        ("login", "done"),
        ("cart", "started"),
        ("cart", "done"),
        ("shipping", "started"),
        ("shipping", "done"),
        ("confirm", "started"),
        ("confirm", "done"),
        ("handoff", "started"),
        ("handoff", "done"),
    ]


async def test_on_step_reports_retries_with_the_attempt_number() -> None:
    calls = {"n": 0}

    async def hook(index: int, method: str, url: str) -> None:
        if url == "login":
            calls["n"] += 1
            if calls["n"] == 1:
                raise UpstreamError

    site = FakeSite(hook=hook)
    steps: list[tuple[str, str, int]] = []

    await _run(site, handoff=True, on_step=lambda s: steps.append((s.step, s.status, s.attempt)))

    login = [s for s in steps if s[0] == "login"]
    assert login == [("login", "started", 1), ("login", "started", 2), ("login", "done", 2)]
