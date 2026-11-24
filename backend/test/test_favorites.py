from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from spider.application.favorites import (
    MAX_FAVORITES_PER_ACCOUNT,
    FavoriteDeps,
    add_favorite,
    delete_account,
    delete_favorite,
    get_notifications,
    list_favorites,
    mark_notifications_read,
    register_account,
    update_favorite,
)
from spider.application.ports import (
    DuplicateAccount,
    DuplicateFavorite,
    EntityNotFound,
    FavoriteLimitReached,
    InvalidTransition,
    LoginFailed,
    UnsupportedPaymentMethod,
)
from spider.application.retry import PreviewRuntime
from spider.application.use_cases import ProductNotFound
from spider.domain.account import Notification
from spider.infrastructure.product_parsers import extract_product_page
from spider.infrastructure.secret_box import FernetSecretBox
from test.fake_repos import MemoryRepos
from test.fakes import PID, PRODUCT_URL, FakeSite, FakeTime, html

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
IN_STOCK = html("product_page_purchasable.html").replace("810297", str(PID))


class FakeClock:
    def __init__(self) -> None:
        self.current = NOW

    def now(self) -> datetime:
        return self.current


def _deps(site: FakeSite | None = None) -> tuple[FavoriteDeps, MemoryRepos, FakeSite, FakeClock]:
    site = site or FakeSite(product_page=IN_STOCK)
    repos = MemoryRepos()
    clock = FakeClock()
    time = FakeTime()
    counter = {"n": 0}

    def new_id() -> str:
        counter["n"] += 1
        return f"id{counter['n']}"

    deps = FavoriteDeps(
        accounts=repos.accounts,
        favorites=repos.favorites,
        keyword_favorites=repos.keyword_favorites,
        notifications=repos.notifications,
        settings=repos.settings,
        secret_box=FernetSecretBox(Fernet.generate_key().decode()),
        clock=clock,
        new_id=new_id,
        client_factory=site.factory,
        extract_product_page=extract_product_page,
        runtime=PreviewRuntime(sleep=time.sleep, rng=lambda: 1.0, now=time),
        login_deadline_seconds=15.0,
    )
    return deps, repos, site, clock


# --- アカウント ---------------------------------------------------------------


async def test_register_account_verifies_the_login_and_stores_the_password_encrypted() -> None:
    deps, repos, site, _ = _deps()

    account = await register_account(deps, "テスト用 A", "a@example.test", "secret-pw")

    assert account.model_dump() == {
        "id": "id1",
        "label": "テスト用 A",
        "email": "a@example.test",
    }
    assert [m for _, m, _, _ in site.log] == ["LOGIN"]
    assert all(c.closed for c in site.clients)
    _, encrypted = await repos.accounts.get_with_secret(account.id) or (None, "")
    assert encrypted and "secret-pw" not in encrypted
    assert deps.secret_box.decrypt(encrypted) == "secret-pw"


async def test_a_failed_login_stores_nothing() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "LOGIN":
            raise LoginFailed

    deps, repos, _, _ = _deps(FakeSite(hook=hook))

    with pytest.raises(LoginFailed):
        await register_account(deps, "A", "a@example.test", "bad")

    assert await repos.accounts.list_all() == []


async def test_the_same_email_cannot_be_registered_twice_and_sends_nothing() -> None:
    deps, _, site, _ = _deps()
    await register_account(deps, "A", "a@example.test", "pw")
    requests = len(site.log)

    with pytest.raises(DuplicateAccount):
        await register_account(deps, "B", "a@example.test", "pw")

    assert len(site.log) == requests


async def test_deleting_an_account_deletes_its_favorites() -> None:
    deps, repos, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    await add_favorite(deps, account.id, PID, "8", None)

    await delete_account(deps, account.id)

    assert await repos.accounts.list_all() == []
    assert await repos.favorites.list_all() == []
    with pytest.raises(EntityNotFound):
        await delete_account(deps, account.id)


async def test_deleting_an_account_also_deletes_its_keyword_favorites() -> None:
    from datetime import UTC, datetime  # noqa: PLC0415

    from spider.domain.keyword_favorite import KeywordFavorite  # noqa: PLC0415

    deps, repos, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    await repos.keyword_favorites.add(
        KeywordFavorite(
            id="k1",
            account_id=account.id,
            keyword="豆本",
            category_id=22,
            category_label="SuperDollfie > 本体",
            payment_method="8",
            price_cap_yen=None,
            enabled=True,
            new_arrival_count=0,
            created_at=datetime(2026, 11, 23, tzinfo=UTC),
        )
    )

    await delete_account(deps, account.id)

    assert await repos.keyword_favorites.list_all() == []


# --- お気に入り ---------------------------------------------------------------


async def test_add_favorite_reads_the_product_and_starts_watching() -> None:
    deps, _, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")

    favorite = await add_favorite(deps, account.id, PID, "3", 1500)

    assert (favorite.account_id, favorite.product_id, favorite.payment_method) == (
        account.id,
        PID,
        "3",
    )
    assert favorite.product_name == "SD/豆本 I-26-11-05-335-KD-ZI"
    assert (favorite.price_cap_yen, favorite.state, favorite.state_version) == (1500, "watching", 0)
    assert favorite.state_changed_at == NOW
    assert await list_favorites(deps, account.id) == [favorite]


async def test_add_favorite_needs_an_existing_account() -> None:
    deps, _, _, _ = _deps()

    with pytest.raises(EntityNotFound):
        await add_favorite(deps, "missing", PID, "8", None)


async def test_the_limit_is_twenty_favorites_per_account() -> None:
    deps, repos, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    await add_favorite(deps, account.id, PID, "8", None)
    # 残りは、サイトへの問い合わせを避けるため、リポジトリへ直接追加する
    base = (await repos.favorites.list_all(account.id))[0]
    for number in range(1, MAX_FAVORITES_PER_ACCOUNT):
        await repos.favorites.add(
            base.model_copy(update={"id": f"x{number}", "product_id": 1000 + number})
        )

    with pytest.raises(FavoriteLimitReached):
        await add_favorite(deps, account.id, PID + 1, "8", None)


async def test_the_same_product_cannot_be_added_twice() -> None:
    deps, _, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    await add_favorite(deps, account.id, PID, "8", None)

    with pytest.raises(DuplicateFavorite):
        await add_favorite(deps, account.id, PID, "8", None)


async def test_a_missing_product_cannot_be_added() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == PRODUCT_URL:
            raise ProductNotFound

    deps, _, _, _ = _deps(FakeSite(product_page=IN_STOCK, hook=hook))
    account = await register_account(deps, "A", "a@example.test", "pw")

    with pytest.raises(ProductNotFound):
        await add_favorite(deps, account.id, PID, "8", None)


@pytest.mark.parametrize(
    ("payment", "reason"),
    [("10000006", "submit"), ("10000050", "submit"), ("10000028", "submit"), ("999", "unknown")],
)
async def test_only_payment_methods_that_can_complete_an_order_are_allowed(
    payment: str, reason: str
) -> None:
    deps, _, site, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    requests = len(site.log)

    with pytest.raises(UnsupportedPaymentMethod) as info:
        await add_favorite(deps, account.id, PID, payment, None)

    assert info.value.reason == reason
    assert len(site.log) == requests


async def test_update_changes_settings_and_can_clear_the_cap() -> None:
    deps, _, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    favorite = await add_favorite(deps, account.id, PID, "8", 1500)

    updated = await update_favorite(
        deps, favorite.id, payment_method_id="1", set_cap=True, price_cap_yen=None, resume=False
    )

    assert (updated.payment_method, updated.price_cap_yen) == ("1", None)
    with pytest.raises(UnsupportedPaymentMethod):
        await update_favorite(
            deps,
            favorite.id,
            payment_method_id="10000006",
            set_cap=False,
            price_cap_yen=None,
            resume=False,
        )


@pytest.mark.parametrize("finished", ["stopped", "rejected", "unknown", "purchased"])
async def test_a_finished_favorite_can_be_resumed_by_the_user(finished: str) -> None:
    deps, repos, _, clock = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    favorite = await add_favorite(deps, account.id, PID, "8", None)
    await repos.favorites.transition(favorite.id, "watching", finished, 0, NOW)  # type: ignore[arg-type]
    clock.current = NOW + timedelta(minutes=5)

    resumed = await update_favorite(
        deps, favorite.id, payment_method_id=None, set_cap=False, price_cap_yen=None, resume=True
    )

    assert resumed.state == "watching"
    assert resumed.state_version == 2


async def test_a_favorite_being_purchased_cannot_be_resumed() -> None:
    deps, repos, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    favorite = await add_favorite(deps, account.id, PID, "8", None)
    await repos.favorites.transition(favorite.id, "watching", "purchasing", 0, NOW)

    with pytest.raises(InvalidTransition):
        await update_favorite(
            deps,
            favorite.id,
            payment_method_id=None,
            set_cap=False,
            price_cap_yen=None,
            resume=True,
        )


async def test_delete_favorite() -> None:
    deps, repos, _, _ = _deps()
    account = await register_account(deps, "A", "a@example.test", "pw")
    favorite = await add_favorite(deps, account.id, PID, "8", None)

    await delete_favorite(deps, favorite.id)

    assert await repos.favorites.list_all() == []
    with pytest.raises(EntityNotFound):
        await delete_favorite(deps, favorite.id)


# --- 通知 ---------------------------------------------------------------------


async def test_notifications_report_the_unread_count_and_can_be_marked_read() -> None:
    deps, repos, _, _ = _deps()
    await repos.notifications.add(
        Notification(
            id="n1", favorite_id=None, kind="purchased", message="m", created_at=NOW, read=False
        )
    )

    items, unread = await get_notifications(deps)
    assert ([n.id for n in items], unread) == (["n1"], 1)

    await mark_notifications_read(deps)

    assert (await get_notifications(deps))[1] == 0
