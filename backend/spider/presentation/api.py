import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, NamedTuple

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, SecretStr, model_validator

from spider.application import favorites as favorite_cases
from spider.application import keyword_favorites as keyword_cases
from spider.application.favorites import FavoriteDeps
from spider.application.keyword_favorites import KeywordFavoriteDeps
from spider.application.login import check_login
from spider.application.ports import (
    DuplicateAccount,
    DuplicateFavorite,
    EntityNotFound,
    FavoriteLimitReached,
    HandoffAndSubmit,
    InvalidTransition,
    LoginFailed,
    NotPurchasable,
    OrderSubmitDisabled,
    PaymentMethodUnavailable,
    PreviewTimeout,
    SecretBoxError,
    SiteClient,
    UnsupportedPaymentMethod,
    UpstreamError,
)
from spider.application.preview import (
    CheckoutParsers,
    PreviewConfig,
    store_pickup_preview,
)
from spider.application.products import get_product, search_products
from spider.application.retry import PreviewRuntime
from spider.application.use_cases import (
    ProductNotFound,
    get_latest_product_name,
    get_purchase_history,
)
from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite
from spider.domain.keyword_favorite import DEFAULT_GENRE_ID, Genre, KeywordFavorite
from spider.domain.order import Order
from spider.domain.payment import DEFAULT_PAYMENT_METHOD_ID, PAYMENT_METHODS, PaymentMethod
from spider.domain.product import PreviewStep, ProductSummary, StorePickupResult

LIST_URL = "https://www.dollyteria.com/product-list/22?view=new"


class Dependencies(NamedTuple):
    """main.py から注入する実装の一式（presentation は infrastructure を import しない）。"""

    client_factory: Callable[[], SiteClient]
    extract_latest_name: Callable[[str], str]
    extract_orders: Callable[[str], list[Order]]
    extract_product_page: Callable[[str, int], ProductSummary]
    extract_search_results: Callable[[str, set[int]], list[ProductSummary]]
    extract_product_ids: Callable[[str], set[int]]
    checkout_parsers: CheckoutParsers
    preview_config: PreviewConfig
    runtime: PreviewRuntime
    login_deadline_seconds: float
    favorite_deps: FavoriteDeps
    keyword_deps: KeywordFavoriteDeps
    on_startup: Callable[[], Awaitable[None]]


class LatestProduct(BaseModel):
    name: str


class LoginRequest(BaseModel):
    email: str
    password: SecretStr


class PreviewRequest(BaseModel):
    """保存済みのアカウント（account_id）か、email / password のどちらかで実行する。"""

    account_id: str | None = None
    email: str | None = None
    password: SecretStr | None = None
    product_id: int
    payment_method: str = DEFAULT_PAYMENT_METHOD_ID
    submit_order: bool = False
    handoff: bool = False

    @model_validator(mode="after")
    def _needs_credentials(self) -> "PreviewRequest":
        if self.account_id is None and (self.email is None or self.password is None):
            raise ValueError("account_id か email / password が必要です")
        return self


class LoginOk(BaseModel):
    ok: bool = True


class AccountRequest(LoginRequest):
    label: str


class FavoriteRequest(BaseModel):
    account_id: str
    product_id: int
    payment_method: str = DEFAULT_PAYMENT_METHOD_ID
    price_cap_yen: int | None = None


class FavoritePatch(BaseModel):
    payment_method: str | None = None
    price_cap_yen: int | None = None
    resume: bool = False


class NotificationList(BaseModel):
    unread: int
    items: list[Notification]


class Unread(BaseModel):
    unread: int


class AutoPurchaseState(BaseModel):
    enabled: bool
    order_submit_allowed: bool
    last_tick_at: datetime | None
    next_nightly_at: datetime


class EnabledRequest(BaseModel):
    enabled: bool


class KeywordFavoriteRequest(BaseModel):
    account_id: str
    keyword: str
    category_id: int = DEFAULT_GENRE_ID
    payment_method: str = DEFAULT_PAYMENT_METHOD_ID
    price_cap_yen: int | None = None


class KeywordFavoritePatch(BaseModel):
    payment_method: str
    price_cap_yen: int | None = None


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


_STREAM_REASON: dict[type[Exception], str] = {
    ProductNotFound: "product_not_found",
    NotPurchasable: "not_purchasable",
    PaymentMethodUnavailable: "payment_method_unavailable",
    UnsupportedPaymentMethod: "unsupported_payment_method",
    PreviewTimeout: "timeout",
    UpstreamError: "upstream_error",
    LoginFailed: "login_failed",
}


def _json_reason(error: Exception) -> str:
    reason = _STREAM_REASON.get(type(error), "error")
    return f'{{"reason":"{reason}"}}'


def create_app(deps: Dependencies) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await deps.on_startup()
        shared = deps.client_factory()
        app.state.shared_client = shared
        try:
            yield
        finally:
            await shared.aclose()

    async def new_client() -> AsyncIterator[SiteClient]:
        client = deps.client_factory()
        try:
            yield client
        finally:
            await client.aclose()

    def shared_client(request: Request) -> SiteClient:
        client: SiteClient = request.app.state.shared_client
        return client

    app = FastAPI(lifespan=lifespan)
    router = APIRouter(prefix="/api")

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/payment-methods")
    async def payment_methods() -> list[PaymentMethod]:
        return list(PAYMENT_METHODS)

    @router.get("/latest-product")
    async def latest_product(
        client: Annotated[SiteClient, Depends(shared_client)],
    ) -> LatestProduct:
        name = await get_latest_product_name(client, LIST_URL, deps.extract_latest_name)
        return LatestProduct(name=name)

    @router.get("/products/{product_id}", response_model=None)
    async def product(
        product_id: int, client: Annotated[SiteClient, Depends(shared_client)]
    ) -> ProductSummary | JSONResponse:
        try:
            return await get_product(client, product_id, deps.extract_product_page)
        except ProductNotFound:
            return _error(404, "product not found")

    @router.get("/products")
    async def products(
        keyword: Annotated[str, Query(min_length=1)],
        client: Annotated[SiteClient, Depends(shared_client)],
    ) -> list[ProductSummary]:
        return await search_products(
            client, keyword, deps.extract_search_results, deps.extract_product_ids
        )

    @router.post("/purchase-history")
    async def purchase_history(
        body: LoginRequest, client: Annotated[SiteClient, Depends(new_client)]
    ) -> list[Order]:
        return await get_purchase_history(
            client, body.email, body.password.get_secret_value(), deps.extract_orders
        )

    @router.post("/login-check")
    async def login_check(
        body: LoginRequest, client: Annotated[SiteClient, Depends(new_client)]
    ) -> LoginOk:
        await check_login(
            client,
            body.email,
            body.password.get_secret_value(),
            runtime=deps.runtime,
            deadline_seconds=deps.login_deadline_seconds,
        )
        return LoginOk()

    async def credentials_of(body: PreviewRequest) -> tuple[str, str]:
        if body.account_id is not None:
            found = await deps.favorite_deps.accounts.get_with_secret(body.account_id)
            if found is None:
                raise EntityNotFound
            account, encrypted = found
            try:
                return account.email, deps.favorite_deps.secret_box.decrypt(encrypted)
            except SecretBoxError:
                raise LoginFailed from None
        assert body.email is not None and body.password is not None  # 検証済み
        return body.email, body.password.get_secret_value()

    @router.post("/store-pickup-preview", response_model=None)
    async def preview(body: PreviewRequest) -> StorePickupResult | JSONResponse:
        email, password = await credentials_of(body)
        try:
            return await store_pickup_preview(
                client_factory=deps.client_factory,
                parsers=deps.checkout_parsers,
                config=deps.preview_config,
                runtime=deps.runtime,
                email=email,
                password=password,
                product_id=body.product_id,
                payment_method_id=body.payment_method,
                submit_order=body.submit_order,
                handoff=body.handoff,
            )
        except ProductNotFound:
            return _error(404, "product not found")

    @router.get("/store-pickup-preview/stream")
    async def preview_stream(
        account_id: str, product_id: int, payment_method: str
    ) -> StreamingResponse:
        # 引き継ぎ（確認画面まで）の進捗を SSE で逐次流す。
        # 資格情報の解決はここで行う（失敗は通常のHTTPエラーになる）。
        email, password = await credentials_of(
            PreviewRequest(
                account_id=account_id, product_id=product_id, payment_method=payment_method
            )
        )
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def on_step(step: PreviewStep) -> None:
            queue.put_nowait(("step", step.model_dump_json()))

        async def run() -> None:
            try:
                result = await store_pickup_preview(
                    client_factory=deps.client_factory,
                    parsers=deps.checkout_parsers,
                    config=deps.preview_config._replace(parallelism=1),
                    runtime=deps.runtime,
                    email=email,
                    password=password,
                    product_id=product_id,
                    payment_method_id=payment_method,
                    submit_order=False,
                    handoff=True,
                    on_step=on_step,
                )
                handoff = result.handoff
                assert handoff is not None  # handoff=True なので必ず入る
                queue.put_nowait(("done", handoff.model_dump_json()))
            except tuple(_STREAM_REASON) as error:
                queue.put_nowait(("error", _json_reason(error)))
            except Exception:  # noqa: BLE001 - 想定外も必ずストリームを閉じる
                queue.put_nowait(("error", '{"reason":"error"}'))
            finally:
                queue.put_nowait(("__end__", ""))

        task = asyncio.create_task(run())

        async def events() -> AsyncIterator[str]:
            try:
                while True:
                    event, data = await queue.get()
                    if event == "__end__":
                        break
                    yield f"event: {event}\ndata: {data}\n\n"
            finally:
                task.cancel()

        return StreamingResponse(events(), media_type="text/event-stream")

    cases = deps.favorite_deps

    @router.post("/accounts")
    async def register_account(body: AccountRequest) -> Account:
        return await favorite_cases.register_account(
            cases, body.label, body.email, body.password.get_secret_value()
        )

    @router.get("/accounts")
    async def list_accounts() -> list[Account]:
        return await favorite_cases.list_accounts(cases)

    @router.delete("/accounts/{account_id}", status_code=204)
    async def delete_account(account_id: str) -> None:
        await favorite_cases.delete_account(cases, account_id)

    @router.post("/favorites", response_model=None)
    async def add_favorite(body: FavoriteRequest) -> Favorite | JSONResponse:
        try:
            return await favorite_cases.add_favorite(
                cases, body.account_id, body.product_id, body.payment_method, body.price_cap_yen
            )
        except ProductNotFound:
            return _error(404, "product not found")

    @router.get("/favorites")
    async def list_favorites(account_id: str | None = None) -> list[Favorite]:
        return await favorite_cases.list_favorites(cases, account_id)

    @router.patch("/favorites/{favorite_id}")
    async def update_favorite(favorite_id: str, body: FavoritePatch) -> Favorite:
        return await favorite_cases.update_favorite(
            cases,
            favorite_id,
            payment_method_id=body.payment_method,
            set_cap="price_cap_yen" in body.model_fields_set,
            price_cap_yen=body.price_cap_yen,
            resume=body.resume,
        )

    @router.delete("/favorites/{favorite_id}", status_code=204)
    async def delete_favorite(favorite_id: str) -> None:
        await favorite_cases.delete_favorite(cases, favorite_id)

    @router.get("/notifications")
    async def notifications() -> NotificationList:
        items, unread = await favorite_cases.get_notifications(cases)
        return NotificationList(unread=unread, items=items)

    @router.post("/notifications/read")
    async def read_notifications() -> Unread:
        await favorite_cases.mark_notifications_read(cases)
        return Unread(unread=0)

    async def auto_purchase_state() -> AutoPurchaseState:
        status = await favorite_cases.auto_purchase_status(
            cases, deps.preview_config.allow_order_submit
        )
        return AutoPurchaseState(**status._asdict())

    router.add_api_route("/auto-purchase/status", auto_purchase_state, methods=["GET"])

    @router.put("/auto-purchase/enabled")
    async def set_auto_purchase(body: EnabledRequest) -> AutoPurchaseState:
        await favorite_cases.set_auto_purchase_enabled(cases, body.enabled)
        return await auto_purchase_state()

    kw = deps.keyword_deps

    @router.get("/genres")
    async def genres() -> list[Genre]:
        return await kw.categories.list_categories()

    @router.post("/keyword-favorites", response_model=None)
    async def add_keyword_favorite(body: KeywordFavoriteRequest) -> KeywordFavorite | JSONResponse:
        try:
            return await keyword_cases.register_keyword_favorite(
                kw,
                body.account_id,
                body.keyword,
                body.category_id,
                body.payment_method,
                body.price_cap_yen,
            )
        except KeyError:
            return _error(422, "unknown_genre")

    @router.get("/keyword-favorites")
    async def list_keyword_favorites(account_id: str | None = None) -> list[KeywordFavorite]:
        return await keyword_cases.list_keyword_favorites(kw, account_id)

    @router.patch("/keyword-favorites/{favorite_id}")
    async def update_keyword_favorite(
        favorite_id: str, body: KeywordFavoritePatch
    ) -> KeywordFavorite:
        return await keyword_cases.update_keyword_favorite(
            kw, favorite_id, payment_method=body.payment_method, price_cap_yen=body.price_cap_yen
        )

    @router.delete("/keyword-favorites/{favorite_id}", status_code=204)
    async def delete_keyword_favorite(favorite_id: str) -> None:
        await keyword_cases.delete_keyword_favorite(kw, favorite_id)

    @router.put("/keyword-favorites/{favorite_id}/enabled")
    async def set_keyword_favorite_enabled(
        favorite_id: str, body: EnabledRequest
    ) -> KeywordFavorite:
        await keyword_cases.set_keyword_favorite_enabled(kw, favorite_id, body.enabled)
        favorite = await kw.keyword_favorites.get(favorite_id)
        if favorite is None:
            raise EntityNotFound
        return favorite

    app.include_router(router)

    @app.exception_handler(LoginFailed)
    async def login_failed(request: Request, exc: LoginFailed) -> JSONResponse:
        return _error(401, "login failed")

    @app.exception_handler(ProductNotFound)
    async def product_not_found(request: Request, exc: ProductNotFound) -> JSONResponse:
        return _error(502, "product not found upstream")

    @app.exception_handler(UpstreamError)
    async def upstream_error(request: Request, exc: UpstreamError) -> JSONResponse:
        return _error(502, "upstream request failed")

    @app.exception_handler(PreviewTimeout)
    async def preview_timeout(request: Request, exc: PreviewTimeout) -> JSONResponse:
        return _error(504, "timed out")

    @app.exception_handler(NotPurchasable)
    async def not_purchasable(request: Request, exc: NotPurchasable) -> JSONResponse:
        return _error(409, "not_purchasable")

    @app.exception_handler(PaymentMethodUnavailable)
    async def payment_unavailable(request: Request, exc: PaymentMethodUnavailable) -> JSONResponse:
        return _error(409, "payment_method_unavailable")

    @app.exception_handler(UnsupportedPaymentMethod)
    async def unsupported_payment(request: Request, exc: UnsupportedPaymentMethod) -> JSONResponse:
        return _error(422, f"unsupported_payment_method:{exc.reason}")

    @app.exception_handler(HandoffAndSubmit)
    async def handoff_and_submit(request: Request, exc: HandoffAndSubmit) -> JSONResponse:
        return _error(422, "handoff_and_submit")

    @app.exception_handler(OrderSubmitDisabled)
    async def submit_disabled(request: Request, exc: OrderSubmitDisabled) -> JSONResponse:
        return _error(403, "order submission is disabled")

    @app.exception_handler(EntityNotFound)
    async def entity_not_found(request: Request, exc: EntityNotFound) -> JSONResponse:
        return _error(404, "not found")

    @app.exception_handler(DuplicateAccount)
    async def duplicate_account(request: Request, exc: DuplicateAccount) -> JSONResponse:
        return _error(409, "duplicate_account")

    @app.exception_handler(DuplicateFavorite)
    async def duplicate_favorite(request: Request, exc: DuplicateFavorite) -> JSONResponse:
        return _error(409, "duplicate_favorite")

    @app.exception_handler(FavoriteLimitReached)
    async def favorite_limit(request: Request, exc: FavoriteLimitReached) -> JSONResponse:
        return _error(409, "favorite_limit")

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(request: Request, exc: InvalidTransition) -> JSONResponse:
        return _error(409, "invalid_transition")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 既定の応答は入力値（パスワード）をそのまま返すため、項目名と理由だけにする
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    return app
