from collections.abc import Callable
from typing import NamedTuple

from spider.application.ports import (
    AccountRepository,
    Clock,
    DuplicateFavorite,
    EntityNotFound,
    FavoriteLimitReached,
    KeywordFavoriteRepository,
    SiteClient,
    UnsupportedPaymentMethod,
)
from spider.application.products import search_products
from spider.application.retry import PreviewRuntime
from spider.domain.keyword_favorite import KeywordFavorite, get_genre
from spider.domain.payment import get_payment_method
from spider.domain.product import ProductSummary

MAX_KEYWORD_FAVORITES = 5


class KeywordFavoriteDeps(NamedTuple):
    keyword_favorites: KeywordFavoriteRepository
    accounts: AccountRepository
    clock: Clock
    new_id: Callable[[], str]
    client_factory: Callable[[], SiteClient]
    extract_search_results: Callable[[str, set[int]], list[ProductSummary]]
    extract_product_ids: Callable[[str], set[int]]
    runtime: PreviewRuntime


def _check_payment_method(payment_method_id: str) -> None:
    """確認画面まで進める支払方法だけを許可する（クレジットカードは不可）。"""
    method = get_payment_method(payment_method_id)  # 未知は KeyError
    if not method.preview_supported:
        raise UnsupportedPaymentMethod("preview")


async def _current_product_ids(
    deps: KeywordFavoriteDeps, keyword: str, category_id: int
) -> set[int]:
    client = deps.client_factory()
    try:
        results = await search_products(
            client,
            keyword,
            deps.extract_search_results,
            deps.extract_product_ids,
            category_id=category_id,
        )
    finally:
        await client.aclose()
    return {p.product_id for p in results}


async def register_keyword_favorite(
    deps: KeywordFavoriteDeps,
    account_id: str,
    keyword: str,
    category_id: int,
    payment_method_id: str,
    price_cap_yen: int | None,
) -> KeywordFavorite:
    genre = get_genre(category_id)  # 未知のジャンルは KeyError
    _check_payment_method(payment_method_id)
    if await deps.accounts.get_with_secret(account_id) is None:
        raise EntityNotFound
    existing = await deps.keyword_favorites.list_all(account_id)
    if len(existing) >= MAX_KEYWORD_FAVORITES:
        raise FavoriteLimitReached
    if any(f.keyword == keyword and f.category_id == category_id for f in existing):
        raise DuplicateFavorite
    baseline = await _current_product_ids(deps, keyword, category_id)
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
    # baseline を伴って1回で作る（作成～基準記録の窓を作らない）
    await deps.keyword_favorites.add(favorite, baseline)
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
