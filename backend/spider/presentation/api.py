from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SecretStr

from spider.application.ports import LoginFailed, SiteClient, UpstreamError
from spider.application.use_cases import (
    ProductNotFound,
    get_latest_product_name,
    get_purchase_history,
)
from spider.domain.order import Order

LIST_URL = "https://www.dollyteria.com/product-list/22?view=new"


class LatestProduct(BaseModel):
    name: str


class LoginRequest(BaseModel):
    email: str
    password: SecretStr


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


def create_app(
    client_factory: Callable[[], SiteClient],
    extract_name: Callable[[str], str],
    extract_orders: Callable[[str], list[Order]],
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        shared = client_factory()
        app.state.shared_client = shared
        try:
            yield
        finally:
            await shared.aclose()

    async def new_client() -> AsyncIterator[SiteClient]:
        client = client_factory()
        try:
            yield client
        finally:
            await client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/latest-product")
    async def latest_product(request: Request) -> LatestProduct:
        client: SiteClient = request.app.state.shared_client
        return LatestProduct(name=await get_latest_product_name(client, LIST_URL, extract_name))

    @app.post("/purchase-history")
    async def purchase_history(
        body: LoginRequest, client: Annotated[SiteClient, Depends(new_client)]
    ) -> list[Order]:
        return await get_purchase_history(
            client, body.email, body.password.get_secret_value(), extract_orders
        )

    @app.exception_handler(LoginFailed)
    async def login_failed(request: Request, exc: LoginFailed) -> JSONResponse:
        return _error(401, "login failed")

    @app.exception_handler(ProductNotFound)
    async def product_not_found(request: Request, exc: ProductNotFound) -> JSONResponse:
        return _error(502, "product not found upstream")

    @app.exception_handler(UpstreamError)
    async def upstream_error(request: Request, exc: UpstreamError) -> JSONResponse:
        return _error(502, "upstream request failed")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 既定の応答は入力値（パスワード）をそのまま返すため、項目名と理由だけにする
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    return app
