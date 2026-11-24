from collections.abc import Callable
from typing import NamedTuple

from spider.application.ports import (
    AccountRepository,
    CategoryProvider,
    Clock,
    DuplicateFavorite,
    EntityNotFound,
    FavoriteLimitReached,
    KeywordFavoriteRepository,
    UnsupportedPaymentMethod,
)
from spider.domain.keyword_favorite import KeywordFavorite
from spider.domain.payment import get_payment_method

MAX_KEYWORD_FAVORITES = 10


class KeywordFavoriteDeps(NamedTuple):
    keyword_favorites: KeywordFavoriteRepository
    accounts: AccountRepository
    categories: CategoryProvider
    clock: Clock
    new_id: Callable[[], str]


def _check_payment_method(payment_method_id: str) -> None:
    """確認画面まで進める支払方法だけを許可する（クレジットカードは不可）。"""
    try:
        method = get_payment_method(payment_method_id)
    except KeyError:
        raise UnsupportedPaymentMethod("unknown") from None
    if not method.preview_supported:
        raise UnsupportedPaymentMethod("preview")


async def register_keyword_favorite(
    deps: KeywordFavoriteDeps,
    account_id: str,
    keyword: str,
    category_id: int,
    payment_method_id: str,
    price_cap_yen: int | None,
) -> KeywordFavorite:
    by_id = {c.category_id: c for c in await deps.categories.list_categories()}
    genre = by_id[category_id]  # 未知のジャンルは KeyError
    _check_payment_method(payment_method_id)
    if await deps.accounts.get_with_secret(account_id) is None:
        raise EntityNotFound
    existing = await deps.keyword_favorites.list_all(account_id)
    if len(existing) >= MAX_KEYWORD_FAVORITES:
        raise FavoriteLimitReached
    if any(f.keyword == keyword and f.category_id == category_id for f in existing):
        raise DuplicateFavorite
    favorite = KeywordFavorite(
        id=deps.new_id(),
        account_id=account_id,
        keyword=keyword,
        category_id=category_id,
        category_label=genre.label,
        payment_method=payment_method_id,
        price_cap_yen=price_cap_yen,
        enabled=True,
        new_arrival_count=0,
        created_at=deps.clock.now(),
    )
    # seen は空で作る。最初の監視で、既存の可能な一致商品も1回ずつトリガーする。
    await deps.keyword_favorites.add(favorite)
    return favorite


async def list_keyword_favorites(
    deps: KeywordFavoriteDeps, account_id: str | None = None
) -> list[KeywordFavorite]:
    return await deps.keyword_favorites.list_all(account_id)


async def update_keyword_favorite(
    deps: KeywordFavoriteDeps,
    favorite_id: str,
    *,
    payment_method: str,
    price_cap_yen: int | None,
) -> KeywordFavorite:
    _check_payment_method(payment_method)
    if not await deps.keyword_favorites.update_settings(favorite_id, payment_method, price_cap_yen):
        raise EntityNotFound
    updated = await deps.keyword_favorites.get(favorite_id)
    if updated is None:
        raise EntityNotFound
    return updated


async def set_keyword_favorite_enabled(
    deps: KeywordFavoriteDeps, favorite_id: str, enabled: bool
) -> None:
    if not await deps.keyword_favorites.set_enabled(favorite_id, enabled):
        raise EntityNotFound


async def delete_keyword_favorite(deps: KeywordFavoriteDeps, favorite_id: str) -> None:
    if await deps.keyword_favorites.get(favorite_id) is None:
        raise EntityNotFound
    await deps.keyword_favorites.delete(favorite_id)
