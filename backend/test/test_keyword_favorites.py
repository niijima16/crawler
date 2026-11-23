from datetime import UTC, datetime

import pytest

from spider.application.keyword_favorites import (
    MAX_KEYWORD_FAVORITES,
    KeywordFavoriteDeps,
    delete_keyword_favorite,
    list_keyword_favorites,
    register_keyword_favorite,
    set_keyword_favorite_enabled,
    update_keyword_favorite,
)
from spider.application.ports import (
    DuplicateFavorite,
    EntityNotFound,
    FavoriteLimitReached,
    UnsupportedPaymentMethod,
)
from spider.application.retry import PreviewRuntime
from spider.domain.account import Account
from spider.infrastructure.product_parsers import extract_product_ids, extract_search_results
from test.fake_repos import MemoryRepos
from test.fakes import FakeTime, html

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 23, 21, 0, tzinfo=UTC)
SEARCH = html("product_list_keyword.html")  # 商品ID 775386/810296/810297 を含む
SITE = "https://www.dollyteria.com"


class FakeClock:
    def now(self) -> datetime:
        return NOW


class SearchClient:
    def __init__(self, body: str) -> None:
        self.requested: list[str] = []
        self._body = body

    async def login(self, email: str, password: str) -> None: ...
    async def post(self, url: str, data: dict[str, str]) -> str:
        raise NotImplementedError

    async def get(self, url: str) -> str:
        self.requested.append(url)
        return self._body

    def get_cookie(self, name: str) -> str | None:
        return None

    async def aclose(self) -> None: ...


def _deps(search_body: str = SEARCH) -> tuple[KeywordFavoriteDeps, MemoryRepos, list[SearchClient]]:
    repos = MemoryRepos()
    clients: list[SearchClient] = []
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"k{counter['n']}"

    def factory() -> SearchClient:
        c = SearchClient(search_body)
        clients.append(c)
        return c

    time = FakeTime()
    deps = KeywordFavoriteDeps(
        keyword_favorites=repos.keyword_favorites,
        accounts=repos.accounts,
        clock=FakeClock(),
        new_id=new_id,
        client_factory=factory,
        extract_search_results=extract_search_results,
        extract_product_ids=extract_product_ids,
        runtime=PreviewRuntime(sleep=time.sleep, rng=lambda: 1.0, now=time),
    )
    return deps, repos, clients


async def _account(repos: MemoryRepos, account_id: str = "a1") -> None:
    await repos.accounts.add(Account(id=account_id, label="A", email=f"{account_id}@x.test"), "ENC")


async def test_register_records_the_current_products_as_baseline() -> None:
    deps, repos, _ = _deps()
    await _account(repos)

    fav = await register_keyword_favorite(deps, "a1", "豆本", 22, "8", 3000)

    assert (fav.keyword, fav.category_id, fav.category_label) == ("豆本", 22, "SuperDollfie > 本体")
    assert (fav.payment_method, fav.price_cap_yen, fav.enabled) == ("8", 3000, True)
    # 登録時点の商品は baseline（seen）に入り、以後の対象外になる
    assert not await repos.keyword_favorites.claim_product(fav.id, 775386)
    assert not await repos.keyword_favorites.claim_product(fav.id, 810297)
    # 登録時に無かった商品は新着として claim できる
    assert await repos.keyword_favorites.claim_product(fav.id, 999999)


async def test_register_needs_an_existing_account() -> None:
    deps, _, _ = _deps()
    with pytest.raises(EntityNotFound):
        await register_keyword_favorite(deps, "missing", "豆本", 22, "8", None)


async def test_register_rejects_an_unknown_genre() -> None:
    deps, repos, _ = _deps()
    await _account(repos)
    with pytest.raises(KeyError):
        await register_keyword_favorite(deps, "a1", "豆本", 999999, "8", None)


@pytest.mark.parametrize("method", ["10000028"])
async def test_register_rejects_a_payment_method_that_cannot_reach_confirmation(
    method: str,
) -> None:
    deps, repos, clients = _deps()
    await _account(repos)
    with pytest.raises(UnsupportedPaymentMethod) as info:
        await register_keyword_favorite(deps, "a1", "豆本", 22, method, None)
    assert info.value.reason == "preview"
    assert clients == []  # サイトへ問い合わせない


@pytest.mark.parametrize("method", ["8", "3", "10000006", "10000002_1"])
async def test_register_allows_methods_that_reach_confirmation(method: str) -> None:
    deps, repos, _ = _deps()
    await _account(repos)
    fav = await register_keyword_favorite(deps, "a1", "豆本", 22, method, None)
    assert fav.payment_method == method


async def test_the_limit_is_five_per_account() -> None:
    deps, repos, _ = _deps()
    await _account(repos)
    for n in range(MAX_KEYWORD_FAVORITES):
        await register_keyword_favorite(deps, "a1", f"kw{n}", 22, "8", None)
    with pytest.raises(FavoriteLimitReached):
        await register_keyword_favorite(deps, "a1", "another", 22, "8", None)


async def test_the_same_keyword_and_genre_cannot_be_registered_twice() -> None:
    deps, repos, _ = _deps()
    await _account(repos)
    await register_keyword_favorite(deps, "a1", "豆本", 22, "8", None)
    with pytest.raises(DuplicateFavorite):
        await register_keyword_favorite(deps, "a1", "豆本", 22, "8", None)
    # ジャンルが違えば登録できる
    await register_keyword_favorite(deps, "a1", "豆本", 136, "8", None)


async def test_list_update_toggle_delete() -> None:
    deps, repos, _ = _deps()
    await _account(repos)
    fav = await register_keyword_favorite(deps, "a1", "豆本", 22, "8", None)

    assert [f.id for f in await list_keyword_favorites(deps, "a1")] == [fav.id]

    updated = await update_keyword_favorite(deps, fav.id, payment_method="3", price_cap_yen=1500)
    assert (updated.payment_method, updated.price_cap_yen) == ("3", 1500)
    with pytest.raises(UnsupportedPaymentMethod):
        await update_keyword_favorite(deps, fav.id, payment_method="10000028", price_cap_yen=None)

    await set_keyword_favorite_enabled(deps, fav.id, False)
    assert not (await repos.keyword_favorites.get(fav.id)).enabled  # type: ignore[union-attr]

    await delete_keyword_favorite(deps, fav.id)
    assert await list_keyword_favorites(deps, "a1") == []
    with pytest.raises(EntityNotFound):
        await delete_keyword_favorite(deps, fav.id)
