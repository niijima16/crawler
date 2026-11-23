import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, NamedTuple

from spider.application.ports import (
    HandoffAndSubmit,
    NotPurchasable,
    OrderSubmitDisabled,
    PaymentMethodUnavailable,
    PreviewTimeout,
    SiteClient,
    UnsupportedPaymentMethod,
    UpstreamError,
)
from spider.application.retry import PreviewRuntime, backoff_delay, retrying
from spider.application.use_cases import SALES_HISTORY_URL, SITE
from spider.domain.payment import PaymentMethod, get_payment_method
from spider.domain.product import (
    CheckoutPreview,
    Handoff,
    OrderForm,
    OrderResult,
    PreviewStep,
    PreviewStepName,
    PreviewStepStatus,
    StorePickupResult,
)

type OnStep = Callable[[PreviewStep], None]
type Emit = Callable[[PreviewStepName, PreviewStepStatus, int], None]

MAX_PARALLELISM = 5
CONFIRM_URL = f"{SITE}/cart/confirm"
CUSTOMER_URL = f"{SITE}/cart/customer"
SHIPPING_URL = f"{SITE}/cart/shipping"


class CheckoutParsers(NamedTuple):
    is_in_cart: Callable[[str, int], bool]
    payment_options: Callable[[str], dict[str, str]]
    confirm: Callable[[str, int], CheckoutPreview]
    order_form: Callable[[str], OrderForm]
    recaptcha_rejected: Callable[[str], bool]
    order_ids: Callable[[str], set[str]]


class PreviewConfig(NamedTuple):
    parallelism: int
    deadline_seconds: float
    history_deadline_seconds: float
    allow_order_submit: bool


class _Reached(NamedTuple):
    client: SiteClient
    preview: CheckoutPreview
    confirm_html: str


class _Attempts:
    def __init__(self) -> None:
        self.count = 0

    def add(self) -> None:
        self.count += 1


def _validate(
    payment_method_id: str, submit_order: bool, handoff: bool, config: PreviewConfig
) -> PaymentMethod:
    if handoff and submit_order:
        raise HandoffAndSubmit
    try:
        method = get_payment_method(payment_method_id)
    except KeyError:
        raise UnsupportedPaymentMethod("unknown") from None
    if not method.preview_supported:
        raise UnsupportedPaymentMethod("preview")
    if submit_order:
        if not config.allow_order_submit:
            raise OrderSubmitDisabled
        if not method.submit_supported:
            raise UnsupportedPaymentMethod("submit")
    return method


async def store_pickup_preview(
    *,
    client_factory: Callable[[], SiteClient],
    parsers: CheckoutParsers,
    config: PreviewConfig,
    runtime: PreviewRuntime,
    email: str,
    password: str,
    product_id: int,
    payment_method_id: str,
    submit_order: bool,
    handoff: bool = False,
    retry_delay: Callable[[int, Callable[[], float]], float] = backoff_delay,
    on_step: OnStep | None = None,
) -> StorePickupResult:
    method = _validate(payment_method_id, submit_order, handoff, config)
    attempts = _Attempts()
    deadline_at = runtime.now() + config.deadline_seconds

    def emit(step: PreviewStepName, status: PreviewStepStatus, attempt: int = 0) -> None:
        if on_step is not None:
            on_step(PreviewStep(step=step, status=status, attempt=attempt))

    async def session() -> _Reached:
        client = client_factory()
        try:
            return await _run_session(
                client,
                parsers,
                runtime,
                attempts,
                deadline_at,
                email,
                password,
                product_id,
                method,
                retry_delay,
                emit,
            )
        except BaseException:
            await asyncio.shield(client.aclose())
            raise

    try:
        async with asyncio.timeout(config.deadline_seconds):
            reached = await _race(session, config.parallelism)
    except TimeoutError:
        raise PreviewTimeout from None

    try:
        if handoff:
            emit("handoff", "started", 1)
            cookie = reached.client.get_cookie("PHPSESSID")
            if cookie is None:
                raise UpstreamError
            emit("handoff", "done", 1)
            return StorePickupResult(
                preview=reached.preview,
                attempts=attempts.count,
                handoff=Handoff(
                    cookie_name="PHPSESSID", cookie_value=cookie, confirm_url=CONFIRM_URL
                ),
            )
        order = (
            await _submit_order(
                reached, parsers, runtime, config.history_deadline_seconds, retry_delay
            )
            if submit_order
            else None
        )
    finally:
        await asyncio.shield(reached.client.aclose())
    return StorePickupResult(preview=reached.preview, attempts=attempts.count, order=order)


async def _run_session(
    client: SiteClient,
    parsers: CheckoutParsers,
    runtime: PreviewRuntime,
    attempts: _Attempts,
    deadline_at: float,
    email: str,
    password: str,
    product_id: int,
    method: PaymentMethod,
    retry_delay: Callable[[int, Callable[[], float]], float] = backoff_delay,
    emit: Emit = lambda step, status, attempt: None,
) -> _Reached:
    async def step[T](label: PreviewStepName, action: Callable[[], Awaitable[T]]) -> T:
        tries = _Attempts()

        def on_attempt() -> None:
            attempts.add()
            tries.add()
            emit(label, "started", tries.count)

        result = await retrying(
            action,
            runtime=runtime,
            deadline_at=deadline_at,
            on_attempt=on_attempt,
            delay=retry_delay,
        )
        emit(label, "done", tries.count)
        return result

    await step("login", lambda: client.login(email, password))
    cart = await step(
        "cart",
        lambda: client.post(
            f"{SITE}/product/{product_id}",
            {
                f"cart_add_{product_id}": "t",
                "cart_operation_page": "product",
                f"cart_addquantity_{product_id}": "1",
                "cart_add_btn": "カートに入れる",
            },
        ),
    )
    if not parsers.is_in_cart(cart, product_id):
        raise NotPurchasable
    shipping = await step("shipping", lambda: client.get(CUSTOMER_URL))
    if method.id not in parsers.payment_options(shipping):
        raise PaymentMethodUnavailable
    confirm_html = await step(
        "confirm",
        lambda: client.post(
            SHIPPING_URL,
            {
                "shippingCount": "1",
                "delivery[1][shipping_list]": "99999999",
                "delivery[1][shipping_method]": "1",
                "delivery[1][shippingdate_ymd]": "",
                "delivery[1][shippingdate_time]": "",
                "pay_procedure": method.id,
                "cart_payment_display": "t",
                "go-next": "次へ",
            },
        ),
    )
    preview = parsers.confirm(confirm_html, product_id)
    if not preview.payment_method.startswith(method.label):
        raise PaymentMethodUnavailable
    return _Reached(client, preview, confirm_html)


async def _race(session: Callable[[], Coroutine[Any, Any, _Reached]], count: int) -> _Reached:
    tasks = [asyncio.create_task(session()) for _ in range(count)]
    pending = set(tasks)
    soft: list[Exception] = []
    winner: _Reached | None = None
    try:
        while pending and winner is None:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            reached: list[_Reached] = []
            hard: BaseException | None = None
            for task in done:
                error = task.exception()
                if error is None:
                    reached.append(task.result())
                elif isinstance(error, UpstreamError | PreviewTimeout):
                    soft.append(error)
                elif hard is None:
                    hard = error
            if hard is not None:
                await _close_all(reached)
                raise hard
            if reached:
                winner = reached[0]
                await _close_all(reached[1:])
    finally:
        for task in pending:
            task.cancel()
        leftovers = await asyncio.gather(*pending, return_exceptions=True)
        await _close_all([r for r in leftovers if isinstance(r, _Reached)])
    if winner is None:
        raise next((e for e in reversed(soft) if isinstance(e, PreviewTimeout)), soft[-1])
    return winner


async def _close_all(reached: list[_Reached]) -> None:
    for item in reached:
        await asyncio.shield(item.client.aclose())


async def _submit_order(
    reached: _Reached,
    parsers: CheckoutParsers,
    runtime: PreviewRuntime,
    history_deadline_seconds: float,
    retry_delay: Callable[[int, Callable[[], float]], float] = backoff_delay,
) -> OrderResult:
    client = reached.client

    async def read_order_ids() -> set[str]:
        html = await retrying(
            lambda: client.get(SALES_HISTORY_URL),
            runtime=runtime,
            deadline_at=runtime.now() + history_deadline_seconds,
            delay=retry_delay,
        )
        return parsers.order_ids(html)

    try:
        before = await read_order_ids()
        form = parsers.order_form(reached.confirm_html)
    except (PreviewTimeout, UpstreamError):
        return OrderResult(status="rejected", reason="history_unavailable")

    response: str | None = None
    try:
        response = await client.post(form.action, dict(form.fields))  # 再送しない
    except UpstreamError:
        pass

    try:
        new_ids = await read_order_ids() - before
    except PreviewTimeout:
        return OrderResult(status="unknown", reason="history_unavailable")
    if new_ids:
        return OrderResult(status="submitted", order_id=max(new_ids, key=_order_key))
    if response is None:
        return OrderResult(status="unknown", reason="no_response")
    if parsers.recaptcha_rejected(response):
        return OrderResult(status="rejected", reason="recaptcha")
    return OrderResult(status="rejected", reason="not_accepted")


def _order_key(order_id: str) -> tuple[int, str]:
    return (len(order_id), order_id)
