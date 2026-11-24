"""リポジトリの契約テスト。

メモリ上のフェイクと、DYNAMODB_ENDPOINT があるときは DynamoDB Local の両方で実行する。
"""

import os
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest

from spider.application.ports import (
    AccountRepository,
    FavoriteRepository,
    KeywordFavoriteRepository,
    NotificationRepository,
    SettingsRepository,
)
from spider.domain.account import Account, Notification
from spider.domain.favorite import Favorite
from spider.domain.keyword_favorite import KeywordFavorite
from test.fake_repos import MemoryRepos

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


class Repos:
    def __init__(
        self,
        accounts: AccountRepository,
        favorites: FavoriteRepository,
        notifications: NotificationRepository,
        settings: SettingsRepository,
        keyword_favorites: "KeywordFavoriteRepository",
    ) -> None:
        self.accounts = accounts
        self.favorites = favorites
        self.notifications = notifications
        self.settings = settings
        self.keyword_favorites = keyword_favorites


def _memory() -> Repos:
    memory = MemoryRepos()
    return Repos(
        memory.accounts,
        memory.favorites,
        memory.notifications,
        memory.settings,
        memory.keyword_favorites,
    )


def _dynamodb() -> Repos:
    from spider.infrastructure.dynamodb_repos import (  # noqa: PLC0415
        build_repositories,
        connect,
        ensure_tables,
    )

    client, resource = connect(os.environ["DYNAMODB_ENDPOINT"], "ap-northeast-1")
    prefix = f"t{uuid.uuid4().hex[:8]}-"
    ensure_tables(client, prefix)
    built = build_repositories(resource, prefix)
    return Repos(
        built.accounts,
        built.favorites,
        built.notifications,
        built.settings,
        built.keyword_favorites,
    )


FACTORIES: list[tuple[str, Callable[[], Repos]]] = [("memory", _memory)]
if os.environ.get("DYNAMODB_ENDPOINT"):
    FACTORIES.append(("dynamodb", _dynamodb))


@pytest.fixture(params=[name for name, _ in FACTORIES])
def repos(request: pytest.FixtureRequest) -> Iterator[Repos]:
    factory = dict(FACTORIES)[request.param]
    yield factory()


def _favorite(fid: str = "f1", account_id: str = "a1", product_id: int = 100) -> Favorite:
    return Favorite(
        id=fid,
        account_id=account_id,
        product_id=product_id,
        product_name=f"商品{product_id}",
        payment_method="8",
        price_cap_yen=None,
        state="watching",
        state_version=0,
        state_changed_at=T0,
    )


def _note(nid: str, minutes: int, read: bool = False) -> Notification:
    return Notification(
        id=nid,
        favorite_id="f1",
        kind="purchased",
        message=f"m{nid}",
        created_at=T0 + timedelta(minutes=minutes),
        read=read,
    )


# --- アカウント ---------------------------------------------------------------


async def test_accounts_store_the_encrypted_password_apart_from_the_account(repos: Repos) -> None:
    account = Account(id="a1", label="テスト用 A", email="a@dollyteria.test")

    await repos.accounts.add(account, "ENCRYPTED")

    assert await repos.accounts.list_all() == [account]
    assert await repos.accounts.get_with_secret("a1") == (account, "ENCRYPTED")
    assert await repos.accounts.get_with_secret("missing") is None


async def test_accounts_can_be_deleted(repos: Repos) -> None:
    await repos.accounts.add(Account(id="a1", label="A", email="a@dollyteria.test"), "X")

    await repos.accounts.delete("a1")

    assert await repos.accounts.list_all() == []


# --- お気に入り ---------------------------------------------------------------


async def test_favorites_add_get_and_list_by_account(repos: Repos) -> None:
    await repos.favorites.add(_favorite("f1", "a1", 100))
    await repos.favorites.add(_favorite("f2", "a2", 200))

    assert await repos.favorites.get("f1") == _favorite("f1", "a1", 100)
    assert await repos.favorites.get("missing") is None
    assert {f.id for f in await repos.favorites.list_all()} == {"f1", "f2"}
    assert [f.id for f in await repos.favorites.list_all("a1")] == ["f1"]


async def test_adding_the_same_favorite_id_twice_fails(repos: Repos) -> None:
    await repos.favorites.add(_favorite("f1"))

    with pytest.raises(Exception):  # noqa: B017, PT011
        await repos.favorites.add(_favorite("f1"))


async def test_only_watching_and_purchasing_favorites_are_active(repos: Repos) -> None:
    for fid in ("w", "p", "s"):
        await repos.favorites.add(_favorite(fid, product_id=ord(fid)))
    await repos.favorites.transition("p", "watching", "purchasing", 0, T0)
    await repos.favorites.transition("s", "watching", "stopped", 0, T0)

    active = await repos.favorites.list_active()

    assert {f.id: f.state for f in active} == {"w": "watching", "p": "purchasing"}


async def test_settings_can_be_updated(repos: Repos) -> None:
    await repos.favorites.add(_favorite("f1"))

    assert await repos.favorites.update_settings("f1", "3", 1500)
    assert not await repos.favorites.update_settings("missing", "3", None)

    favorite = await repos.favorites.get("f1")
    assert favorite is not None
    assert (favorite.payment_method, favorite.price_cap_yen) == ("3", 1500)


async def test_transition_is_conditional_on_state_and_version(repos: Repos) -> None:
    await repos.favorites.add(_favorite("f1"))
    later = T0 + timedelta(minutes=1)

    assert await repos.favorites.transition("f1", "watching", "purchasing", 0, later)
    # 同じバージョン・同じ元の状態での2回目は失敗する（二重購入の防止）
    assert not await repos.favorites.transition("f1", "watching", "purchasing", 0, later)
    # 元の状態が違っても失敗する
    assert not await repos.favorites.transition("f1", "watching", "stopped", 1, later)

    favorite = await repos.favorites.get("f1")
    assert favorite is not None
    assert (favorite.state, favorite.state_version, favorite.state_changed_at) == (
        "purchasing",
        1,
        later,
    )


async def test_exactly_one_of_two_concurrent_claims_wins(repos: Repos) -> None:
    import asyncio  # noqa: PLC0415

    await repos.favorites.add(_favorite("f1"))

    results = await asyncio.gather(
        repos.favorites.transition("f1", "watching", "purchasing", 0, T0),
        repos.favorites.transition("f1", "watching", "purchasing", 0, T0),
    )

    assert sorted(results) == [False, True]


async def test_favorites_can_be_deleted_individually_and_by_account(repos: Repos) -> None:
    for fid, account in (("f1", "a1"), ("f2", "a1"), ("f3", "a2")):
        await repos.favorites.add(_favorite(fid, account, ord(fid[-1])))

    await repos.favorites.delete("f1")
    assert {f.id for f in await repos.favorites.list_all()} == {"f2", "f3"}

    await repos.favorites.delete_for_account("a1")
    assert [f.id for f in await repos.favorites.list_all()] == ["f3"]


# --- 通知 ---------------------------------------------------------------------


async def test_notifications_are_listed_newest_first_with_a_limit(repos: Repos) -> None:
    for nid, minutes in (("n1", 1), ("n3", 3), ("n2", 2)):
        await repos.notifications.add(_note(nid, minutes))

    assert [n.id for n in await repos.notifications.list_all()] == ["n3", "n2", "n1"]
    assert [n.id for n in await repos.notifications.list_all(limit=2)] == ["n3", "n2"]


async def test_notifications_can_be_marked_read(repos: Repos) -> None:
    await repos.notifications.add(_note("n1", 1))
    await repos.notifications.add(_note("n2", 2, read=True))
    assert await repos.notifications.unread_count() == 1

    await repos.notifications.mark_all_read()

    assert await repos.notifications.unread_count() == 0
    assert all(n.read for n in await repos.notifications.list_all())


# --- 設定 ---------------------------------------------------------------------


async def test_settings_default_to_enabled_and_no_tick(repos: Repos) -> None:
    assert await repos.settings.auto_purchase_enabled() is True
    assert await repos.settings.last_tick_at() is None


async def test_settings_are_persisted(repos: Repos) -> None:
    await repos.settings.set_auto_purchase_enabled(False)
    await repos.settings.record_tick(T0)

    assert await repos.settings.auto_purchase_enabled() is False
    assert await repos.settings.last_tick_at() == T0


async def test_an_empty_id_is_simply_not_found(repos: Repos) -> None:
    assert await repos.accounts.get_with_secret("") is None
    assert await repos.favorites.get("") is None
    assert not await repos.favorites.update_settings("", "8", None)
    assert not await repos.favorites.transition("", "watching", "stopped", 0, T0)


# --- キーワードお気に入り -----------------------------------------------------


def _keyword_fav(
    kid: str = "k1", account_id: str = "a1", keyword: str = "豆本"
) -> "KeywordFavorite":
    return KeywordFavorite(
        id=kid,
        account_id=account_id,
        keyword=keyword,
        category_id=22,
        category_label="SuperDollfie > 本体",
        payment_method="8",
        price_cap_yen=None,
        enabled=True,
        new_arrival_count=0,
        created_at=T0,
    )


async def test_keyword_favorites_crud(repos: Repos) -> None:
    await repos.keyword_favorites.add(_keyword_fav("k1", "a1"))
    await repos.keyword_favorites.add(_keyword_fav("k2", "a2"))

    assert await repos.keyword_favorites.get("k1") == _keyword_fav("k1", "a1")
    assert await repos.keyword_favorites.get("missing") is None
    assert [k.id for k in await repos.keyword_favorites.list_all("a1")] == ["k1"]
    assert {k.id for k in await repos.keyword_favorites.list_all()} == {"k1", "k2"}


async def test_keyword_favorite_enabled_filter_and_toggle(repos: Repos) -> None:
    await repos.keyword_favorites.add(_keyword_fav("k1"))
    await repos.keyword_favorites.add(_keyword_fav("k2"))
    await repos.keyword_favorites.set_enabled("k2", False)

    assert {k.id for k in await repos.keyword_favorites.list_enabled()} == {"k1"}


async def test_keyword_favorite_update_and_delete(repos: Repos) -> None:
    await repos.keyword_favorites.add(_keyword_fav("k1", "a1"))
    await repos.keyword_favorites.add(_keyword_fav("k2", "a1"))

    assert await repos.keyword_favorites.update_settings("k1", "3", 1500)
    updated = await repos.keyword_favorites.get("k1")
    assert updated is not None
    assert (updated.payment_method, updated.price_cap_yen) == ("3", 1500)

    await repos.keyword_favorites.delete("k1")
    assert await repos.keyword_favorites.get("k1") is None

    await repos.keyword_favorites.delete_for_account("a1")
    assert await repos.keyword_favorites.list_all() == []


async def test_claim_product_succeeds_once(repos: Repos) -> None:
    await repos.keyword_favorites.add(_keyword_fav("k1"))

    assert await repos.keyword_favorites.claim_product("k1", 100)
    assert not await repos.keyword_favorites.claim_product("k1", 100)  # 2回目は失敗
    assert await repos.keyword_favorites.claim_product("k1", 200)


async def test_exactly_one_of_two_concurrent_claims_wins_keyword(repos: Repos) -> None:
    import asyncio  # noqa: PLC0415

    await repos.keyword_favorites.add(_keyword_fav("k1"))

    results = await asyncio.gather(
        repos.keyword_favorites.claim_product("k1", 100),
        repos.keyword_favorites.claim_product("k1", 100),
    )

    assert sorted(results) == [False, True]


async def test_bump_new_arrival(repos: Repos) -> None:
    await repos.keyword_favorites.add(_keyword_fav("k1"))

    await repos.keyword_favorites.bump_new_arrival("k1")
    await repos.keyword_favorites.bump_new_arrival("k1")

    favorite = await repos.keyword_favorites.get("k1")
    assert favorite is not None
    assert favorite.new_arrival_count == 2


async def test_notifications_keep_product_and_payment(repos: Repos) -> None:
    await repos.notifications.add(
        Notification(
            id="n1",
            favorite_id="k1",
            kind="new_arrival",
            message="m",
            created_at=T0,
            read=False,
            product_id=807736,
            payment_method="8",
        )
    )

    items = await repos.notifications.list_all()
    assert (items[0].product_id, items[0].payment_method) == (807736, "8")
