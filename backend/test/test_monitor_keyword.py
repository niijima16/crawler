from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest

from spider.application.monitor import MonitorDeps, check_tick, nightly_check
from spider.application.ports import UpstreamError
from spider.application.preview import CheckoutParsers, PreviewConfig
from spider.application.retry import PreviewRuntime
from spider.domain.account import Notification
from spider.domain.keyword_favorite import KeywordFavorite
from spider.infrastructure.history_parser import extract_orders
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
from test.fake_repos import MemoryRepos
from test.fakes import FakeTime, html

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 23, 21, 0, tzinfo=UTC)
# 商品ID 775386(440円,在庫あり) / 810296(550円,売り切れ) / 810297(550円,在庫あり)
SEARCH = html("product_list_keyword.html")
IN_STOCK = html("product_list_keyword_available.html")  # 775386, 810297


class FakeClock:
    def now(self) -> datetime:
        return NOW


class SearchSite:
    def __init__(
        self,
        all_body: str,
        stock_body: str,
        hook: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.all = all_body
        self.stock = stock_body
        self.hook = hook
        self.gets: list[str] = []

    def factory(self) -> "SearchClient":
        return SearchClient(self)


class SearchClient:
    def __init__(self, site: SearchSite) -> None:
        self._site = site
        self.closed = False

    async def login(self, email: str, password: str) -> None: ...
    async def post(self, url: str, data: dict[str, str]) -> str:
        raise NotImplementedError

    async def get(self, url: str) -> str:
        self._site.gets.append(url)
        if self._site.hook:
            await self._site.hook(url)
        return self._site.stock if "available=1" in url else self._site.all

    def get_cookie(self, name: str) -> str | None:
        return None

    async def aclose(self) -> None:
        self.closed = True


def _deps(site: SearchSite) -> tuple[MonitorDeps, MemoryRepos]:
    repos = MemoryRepos()
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"n{counter['n']}"

    t = FakeTime()
    deps = MonitorDeps(
        favorites=repos.favorites,
        accounts=repos.accounts,
        notifications=repos.notifications,
        settings=repos.settings,
        secret_box=FernetSecretBox(
            __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode()
        ),
        clock=FakeClock(),
        client_factory=site.factory,
        extract_product_page=extract_product_page,
        checkout_parsers=CheckoutParsers(
            is_in_cart=is_in_cart,
            payment_options=extract_payment_options,
            confirm=extract_confirm,
            order_form=extract_order_form,
            recaptcha_rejected=is_recaptcha_rejected,
            order_ids=lambda page: {o.order_id for o in extract_orders(page)},
        ),
        runtime=PreviewRuntime(sleep=t.sleep, rng=lambda: 1.0, now=t),
        preview_config=PreviewConfig(
            parallelism=3,
            deadline_seconds=60.0,
            history_deadline_seconds=10.0,
            allow_order_submit=False,
        ),
        tick_deadline_seconds=20.0,
        stale_purchasing_seconds=900.0,
        nightly_parallelism=10,
        nightly_retry_interval_seconds=0.1,
        keyword_favorites=repos.keyword_favorites,
        extract_search_results=extract_search_results,
        extract_product_ids=extract_product_ids,
        new_id=new_id,
    )
    return deps, repos


async def _add_kf(
    repos: MemoryRepos,
    *,
    cap: int | None = None,
    enabled: bool = True,
    seen: set[int] | None = None,
) -> KeywordFavorite:
    fav = KeywordFavorite(
        id="k1",
        account_id="a1",
        keyword="豆本",
        category_id=22,
        category_label="SuperDollfie > 本体",
        payment_method="8",
        price_cap_yen=cap,
        enabled=enabled,
        new_arrival_count=0,
        created_at=NOW,
    )
    await repos.keyword_favorites.add(fav)
    if seen:
        await repos.keyword_favorites.mark_seen("k1", seen)
    return fav


async def _notes(repos: MemoryRepos) -> list[Notification]:
    return await repos.notifications.list_all()


async def test_new_in_stock_arrivals_are_notified_and_not_purchased() -> None:
    site = SearchSite(SEARCH, IN_STOCK)
    deps, repos = _deps(site)
    await _add_kf(repos)  # baseline 空 → 在庫ありの新着 775386・810297 が対象

    await check_tick(deps)

    notes = await _notes(repos)
    assert {n.kind for n in notes} == {"new_arrival"}
    assert {n.product_id for n in notes} == {775386, 810297}  # 売り切れ 810296 は含まない
    assert all(n.payment_method == "8" for n in notes)
    # 購入（確認画面への POST）はしない: SearchClient は post を実装していない＝呼ばれていない
    fav = await repos.keyword_favorites.get("k1")
    assert fav is not None and fav.new_arrival_count == 2


async def test_already_seen_products_are_not_renotified() -> None:
    site = SearchSite(SEARCH, IN_STOCK)
    deps, repos = _deps(site)
    await _add_kf(repos, seen={775386, 810297})

    await check_tick(deps)

    assert await _notes(repos) == []


async def test_each_arrival_is_notified_once_even_under_concurrency() -> None:
    import asyncio

    site = SearchSite(SEARCH, IN_STOCK)
    deps, repos = _deps(site)
    await _add_kf(repos)

    await asyncio.gather(check_tick(deps), nightly_check(deps))

    ids = [n.product_id for n in await _notes(repos) if n.product_id is not None]
    assert sorted(ids) == [775386, 810297]  # 重複なし


async def test_price_over_the_cap_is_skipped_and_marked_seen() -> None:
    site = SearchSite(SEARCH, IN_STOCK)
    deps, repos = _deps(site)
    await _add_kf(repos, cap=500)  # 775386=440 は OK、810297=550 は上限超

    await check_tick(deps)

    notes = await _notes(repos)
    by_id = {n.product_id: n.kind for n in notes}
    assert by_id == {775386: "new_arrival", 810297: "skipped_price_cap"}
    # 両方 seen 済み（再通知されない）
    assert not await repos.keyword_favorites.claim_product("k1", 775386)
    assert not await repos.keyword_favorites.claim_product("k1", 810297)


async def test_disabled_keyword_favorites_are_ignored() -> None:
    site = SearchSite(SEARCH, IN_STOCK)
    deps, repos = _deps(site)
    await _add_kf(repos, enabled=False)

    await check_tick(deps)

    assert site.gets == []
    assert await _notes(repos) == []


async def test_master_switch_off_does_not_notify_or_advance_seen() -> None:
    site = SearchSite(SEARCH, IN_STOCK)
    deps, repos = _deps(site)
    await _add_kf(repos)
    await repos.settings.set_auto_purchase_enabled(False)

    await check_tick(deps)

    assert await _notes(repos) == []
    assert await repos.keyword_favorites.claim_product("k1", 775386)  # まだ seen に入っていない


async def test_a_search_503_skips_this_round_without_notifying() -> None:
    async def hook(url: str) -> None:
        raise UpstreamError

    site = SearchSite(SEARCH, IN_STOCK, hook=hook)
    deps, repos = _deps(site)
    await _add_kf(repos)

    await check_tick(deps)

    assert await _notes(repos) == []
    assert await repos.keyword_favorites.claim_product("k1", 775386)
