from collections.abc import Callable
from datetime import datetime
from typing import NamedTuple

from spider.application.login import check_login
from spider.application.ports import (
    AccountRepository,
    Clock,
    DuplicateAccount,
    DuplicateFavorite,
    EntityNotFound,
    FavoriteLimitReached,
    FavoriteRepository,
    InvalidTransition,
    NotificationRepository,
    SecretBox,
    SettingsRepository,
    SiteClient,
    UnsupportedPaymentMethod,
)
from spider.application.products import get_product
from spider.application.retry import PreviewRuntime
from spider.application.schedule import next_nightly
from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite, can_transition
from spider.domain.payment import get_payment_method
from spider.domain.product import ProductSummary

MAX_FAVORITES_PER_ACCOUNT = 20


class FavoriteDeps(NamedTuple):
    accounts: AccountRepository
    favorites: FavoriteRepository
    notifications: NotificationRepository
    settings: SettingsRepository
    secret_box: SecretBox
    clock: Clock
    new_id: Callable[[], str]
    client_factory: Callable[[], SiteClient]
    extract_product_page: Callable[[str, int], ProductSummary]
    runtime: PreviewRuntime
    login_deadline_seconds: float


class AutoPurchaseStatus(NamedTuple):
    enabled: bool
    order_submit_allowed: bool
    last_tick_at: datetime | None
    next_nightly_at: datetime


# --- アカウント ---------------------------------------------------------------


async def register_account(deps: FavoriteDeps, label: str, email: str, password: str) -> Account:
    """ログインできることを確認してから、パスワードを暗号化して保存する。"""
    if any(a.email == email for a in await deps.accounts.list_all()):
        raise DuplicateAccount
    client = deps.client_factory()
    try:
        await check_login(
            client,
            email,
            password,
            runtime=deps.runtime,
            deadline_seconds=deps.login_deadline_seconds,
        )
    finally:
        await client.aclose()
    account = Account(id=deps.new_id(), label=label, email=email)
    await deps.accounts.add(account, deps.secret_box.encrypt(password))
    return account


async def list_accounts(deps: FavoriteDeps) -> list[Account]:
    return await deps.accounts.list_all()


async def delete_account(deps: FavoriteDeps, account_id: str) -> None:
    if await deps.accounts.get_with_secret(account_id) is None:
        raise EntityNotFound
    await deps.favorites.delete_for_account(account_id)
    await deps.accounts.delete(account_id)


# --- お気に入り ---------------------------------------------------------------


def _check_payment_method(payment_method_id: str) -> None:
    """自動購入は注文確定まで進むため、サイト内で完結する支払方法だけを許可する。"""
    try:
        method = get_payment_method(payment_method_id)
    except KeyError:
        raise UnsupportedPaymentMethod("unknown") from None
    if not method.submit_supported:
        raise UnsupportedPaymentMethod("submit")


async def add_favorite(
    deps: FavoriteDeps,
    account_id: str,
    product_id: int,
    payment_method_id: str,
    price_cap_yen: int | None,
) -> Favorite:
    if await deps.accounts.get_with_secret(account_id) is None:
        raise EntityNotFound
    _check_payment_method(payment_method_id)
    existing = await deps.favorites.list_all(account_id)
    if len(existing) >= MAX_FAVORITES_PER_ACCOUNT:
        raise FavoriteLimitReached
    if any(f.product_id == product_id for f in existing):
        raise DuplicateFavorite
    client = deps.client_factory()
    try:
        product = await get_product(client, product_id, deps.extract_product_page)
    finally:
        await client.aclose()
    favorite = Favorite(
        id=deps.new_id(),
        account_id=account_id,
        product_id=product_id,
        product_name=product.name,
        payment_method=payment_method_id,
        price_cap_yen=price_cap_yen,
        state="watching",
        state_version=0,
        state_changed_at=deps.clock.now(),
    )
    await deps.favorites.add(favorite)
    return favorite


async def list_favorites(deps: FavoriteDeps, account_id: str | None = None) -> list[Favorite]:
    return await deps.favorites.list_all(account_id)


async def update_favorite(
    deps: FavoriteDeps,
    favorite_id: str,
    *,
    payment_method_id: str | None,
    set_cap: bool,
    price_cap_yen: int | None,
    resume: bool,
) -> Favorite:
    favorite = await deps.favorites.get(favorite_id)
    if favorite is None:
        raise EntityNotFound
    if payment_method_id is not None:
        _check_payment_method(payment_method_id)
    if resume and favorite.state == "purchasing":
        raise InvalidTransition
    await deps.favorites.update_settings(
        favorite_id,
        payment_method_id or favorite.payment_method,
        price_cap_yen if set_cap else favorite.price_cap_yen,
    )
    if resume and favorite.state != "watching":
        if not can_transition(favorite.state, "watching") or not await deps.favorites.transition(
            favorite_id, favorite.state, "watching", favorite.state_version, deps.clock.now()
        ):
            raise InvalidTransition
    updated = await deps.favorites.get(favorite_id)
    if updated is None:
        raise EntityNotFound
    return updated


async def delete_favorite(deps: FavoriteDeps, favorite_id: str) -> None:
    if await deps.favorites.get(favorite_id) is None:
        raise EntityNotFound
    await deps.favorites.delete(favorite_id)


# --- 通知・状態 ---------------------------------------------------------------


async def get_notifications(deps: FavoriteDeps) -> tuple[list[Notification], int]:
    return await deps.notifications.list_all(), await deps.notifications.unread_count()


async def mark_notifications_read(deps: FavoriteDeps) -> None:
    await deps.notifications.mark_all_read()


async def auto_purchase_status(
    deps: FavoriteDeps, order_submit_allowed: bool
) -> AutoPurchaseStatus:
    return AutoPurchaseStatus(
        enabled=await deps.settings.auto_purchase_enabled(),
        order_submit_allowed=order_submit_allowed,
        last_tick_at=await deps.settings.last_tick_at(),
        next_nightly_at=next_nightly(deps.clock.now()),
    )


async def set_auto_purchase_enabled(deps: FavoriteDeps, enabled: bool) -> None:
    await deps.settings.set_auto_purchase_enabled(enabled)
