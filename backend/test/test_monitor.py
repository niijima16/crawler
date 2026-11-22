import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from spider.application.monitor import MonitorDeps, check_tick, nightly_check
from spider.application.ports import LoginFailed, UpstreamError
from spider.application.preview import CheckoutParsers, PreviewConfig
from spider.application.retry import PreviewRuntime
from spider.application.use_cases import ProductNotFound
from spider.domain.account import Account
from spider.domain.favorite import Favorite
from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.product_parsers import (
    extract_confirm,
    extract_order_form,
    extract_payment_options,
    extract_product_page,
    is_in_cart,
    is_recaptcha_rejected,
)
from spider.infrastructure.secret_box import FernetSecretBox
from test.fake_repos import MemoryRepos
from test.fakes import CONFIRM_URL, PID, PRODUCT_URL, FakeSite, FakeTime, html

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
IN_STOCK = html("product_page_purchasable.html").replace("810297", str(PID))
SOLD_OUT = html("product_page_soldout.html").replace("810296", str(PID))
PARSERS = CheckoutParsers(
    is_in_cart=is_in_cart,
    payment_options=extract_payment_options,
    confirm=extract_confirm,
    order_form=extract_order_form,
    recaptcha_rejected=is_recaptcha_rejected,
    order_ids=lambda page: {o.order_id for o in extract_orders(page)},
)


class FakeClock:
    def __init__(self) -> None:
        self.current = NOW

    def now(self) -> datetime:
        return self.current


class Env:
    def __init__(self, site: FakeSite, *, allow: bool = True, parallelism: int = 3) -> None:
        self.repos = MemoryRepos()
        self.site = site
        self.clock = FakeClock()
        self.key = Fernet.generate_key().decode()
        self.box = FernetSecretBox(self.key)
        self.counter = 0
        time = FakeTime()
        self.deps = MonitorDeps(
            favorites=self.repos.favorites,
            accounts=self.repos.accounts,
            notifications=self.repos.notifications,
            settings=self.repos.settings,
            secret_box=self.box,
            clock=self.clock,
            client_factory=site.factory,
            extract_product_page=extract_product_page,
            checkout_parsers=PARSERS,
            runtime=PreviewRuntime(sleep=time.sleep, rng=lambda: 1.0, now=time),
            preview_config=PreviewConfig(
                parallelism=parallelism,
                deadline_seconds=60.0,
                history_deadline_seconds=10.0,
                allow_order_submit=allow,
            ),
            tick_deadline_seconds=20.0,
            stale_purchasing_seconds=900.0,
            new_id=self._next_id,
        )

    def _next_id(self) -> str:
        self.counter += 1
        return f"n{self.counter}"

    async def account(self, account_id: str = "a1", password: str = "secret-pw") -> None:
        await self.repos.accounts.add(
            Account(id=account_id, label="テスト用", email=f"{account_id}@example.test"),
            self.box.encrypt(password),
        )

    async def favorite(
        self,
        fid: str = "f1",
        *,
        account_id: str = "a1",
        product_id: int = PID,
        payment: str = "8",
        cap: int | None = None,
        state: str = "watching",
        changed: datetime = NOW,
    ) -> None:
        await self.repos.favorites.add(
            Favorite(
                id=fid,
                account_id=account_id,
                product_id=product_id,
                product_name="SD16/OF:靴",
                payment_method=payment,
                price_cap_yen=cap,
                state=state,  # type: ignore[arg-type]
                state_version=0,
                state_changed_at=changed,
            )
        )

    async def state(self, fid: str = "f1") -> str:
        favorite = await self.repos.favorites.get(fid)
        assert favorite is not None
        return favorite.state

    async def kinds(self) -> list[str]:
        return [n.kind for n in await self.repos.notifications.list_all()]


async def _env(**site_kwargs: object) -> Env:
    allow = bool(site_kwargs.pop("allow", True))
    parallelism = int(site_kwargs.pop("parallelism", 3))  # type: ignore[call-overload]
    site = FakeSite(product_page=IN_STOCK, other_product_page=SOLD_OUT, **site_kwargs)  # type: ignore[arg-type]
    env = Env(site, allow=allow, parallelism=parallelism)
    await env.account()
    await env.favorite()
    return env


# --- 何も起きない場合は、書き込みも通知もしない -------------------------------------


async def test_nothing_is_written_while_the_product_is_not_purchasable() -> None:
    env = await _env()
    env.site._product_page = SOLD_OUT  # noqa: SLF001
    writes = env.repos.writes.count

    await check_tick(env.deps)

    assert env.repos.writes.count == writes + 1  # 心拍（最初の1回）だけ
    assert await env.kinds() == []
    assert await env.state() == "watching"


async def test_the_heartbeat_is_written_at_most_once_every_five_minutes() -> None:
    env = await _env()
    env.site._product_page = SOLD_OUT  # noqa: SLF001

    await check_tick(env.deps)
    after_first = env.repos.writes.count
    env.clock.current += timedelta(minutes=1)
    await check_tick(env.deps)
    assert env.repos.writes.count == after_first

    env.clock.current += timedelta(minutes=5)
    await check_tick(env.deps)
    assert env.repos.writes.count == after_first + 1


async def test_a_temporary_upstream_error_is_skipped_silently() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == PRODUCT_URL:
            raise UpstreamError

    env = await _env(hook=hook)
    writes = env.repos.writes.count

    await check_tick(env.deps)

    assert env.repos.writes.count == writes + 1  # 心拍だけ
    assert await env.kinds() == []
    assert await env.state() == "watching"


async def test_everything_is_skipped_while_the_master_switch_is_off() -> None:
    env = await _env()
    await env.repos.settings.set_auto_purchase_enabled(False)
    writes = env.repos.writes.count

    await check_tick(env.deps)

    assert env.site.clients == []
    assert env.repos.writes.count == writes + 1  # 心拍だけ
    assert await env.kinds() == []


# --- 購入 ---------------------------------------------------------------------


async def test_a_purchasable_product_is_bought_and_the_result_is_notified() -> None:
    env = await _env()

    await check_tick(env.deps)

    assert await env.state() == "purchased"
    notes = await env.repos.notifications.list_all()
    assert [n.kind for n in notes] == ["purchased"]
    assert "96301" in notes[0].message
    assert env.site.order_posts == 1


async def test_two_runs_at_the_same_time_buy_only_once() -> None:
    env = await _env()

    await asyncio.gather(check_tick(env.deps), nightly_check(env.deps))

    assert env.site.order_posts == 1
    assert await env.kinds() == ["purchased"]


async def test_a_recaptcha_rejection_is_recorded_as_rejected() -> None:
    env = await _env(accept_order=False, order_response="cart_confirm_recaptcha_failed.html")

    await check_tick(env.deps)

    assert await env.state() == "rejected"
    notes = await env.repos.notifications.list_all()
    assert [n.kind for n in notes] == ["rejected"]
    assert "reCAPTCHA" in notes[0].message
    assert len(env.site.requests("POST", CONFIRM_URL)) == 1


async def test_an_unknown_order_result_is_recorded_as_unknown() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "POST" and url == CONFIRM_URL:
            raise UpstreamError

    env = await _env(accept_order=False, hook=hook)

    await check_tick(env.deps)

    assert await env.state() == "unknown"
    assert await env.kinds() == ["unknown"]


async def test_the_order_is_not_sent_when_the_history_cannot_be_read() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and "sales-history" in url:
            raise UpstreamError

    env = await _env(hook=hook)

    await check_tick(env.deps)

    assert env.site.order_posts == 0
    assert await env.state() == "watching"  # 次の監視で再試行する
    assert await env.kinds() == []


# --- 安全策 -------------------------------------------------------------------


async def test_a_price_above_the_cap_is_not_bought() -> None:
    env = await _env()
    await env.repos.favorites.delete("f1")
    await env.favorite(cap=1000)  # 商品ページの価格は 550 円

    await check_tick(env.deps)
    assert await env.state() == "purchased"  # 550 <= 1000

    env2 = await _env()
    await env2.repos.favorites.delete("f1")
    await env2.favorite(cap=100)

    await check_tick(env2.deps)

    assert await env2.state() == "stopped"
    assert await env2.kinds() == ["skipped_price_cap"]
    assert env2.site.order_posts == 0
    assert [m for _, m, _, _ in env2.site.log if m == "LOGIN"] == []


async def test_nothing_is_bought_when_order_submission_is_not_allowed() -> None:
    env = await _env(allow=False)

    await check_tick(env.deps)

    assert await env.state() == "stopped"
    assert await env.kinds() == ["submit_disabled"]
    assert env.site.log and all(m != "LOGIN" for _, m, _, _ in env.site.log)


async def test_a_login_failure_stops_every_favorite_of_the_account_without_retrying() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "LOGIN":
            raise LoginFailed

    env = await _env(hook=hook)
    await env.favorite("f2", product_id=PID + 1)  # 同じアカウントの別のお気に入り
    await env.account("a2")
    await env.favorite("f3", account_id="a2", product_id=PID + 2)

    await check_tick(env.deps)

    assert await env.state("f1") == "stopped"
    assert await env.state("f2") == "stopped"
    assert await env.state("f3") == "watching"  # 別のアカウントは止めない
    kinds = await env.kinds()
    assert kinds.count("account_stopped") == 1
    assert len([1 for _, m, _, _ in env.site.log if m == "LOGIN"]) == 1


async def test_a_credential_that_cannot_be_decrypted_stops_the_account() -> None:
    env = await _env()
    env.deps = env.deps._replace(secret_box=FernetSecretBox(Fernet.generate_key().decode()))

    await check_tick(env.deps)

    assert await env.state() == "stopped"
    assert await env.kinds() == ["account_stopped"]


async def test_a_product_that_disappeared_is_stopped_and_notified() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "GET" and url == PRODUCT_URL:
            raise ProductNotFound

    env = await _env(hook=hook)

    await check_tick(env.deps)

    assert await env.state() == "stopped"
    assert await env.kinds() == ["rejected"]


async def test_cart_failures_go_back_to_watching_without_notifying() -> None:
    env = await _env(cart="product_page_soldout.html")

    await check_tick(env.deps)

    assert await env.state() == "watching"
    assert await env.kinds() == []


async def test_an_unavailable_payment_method_stops_the_favorite() -> None:
    env = await _env(shipping="cart_shipping_no_pickup.html")

    await check_tick(env.deps)

    assert await env.state() == "stopped"
    assert await env.kinds() == ["rejected"]


async def test_a_timeout_goes_back_to_watching_without_notifying() -> None:
    async def hook(index: int, method: str, url: str) -> None:
        if method == "LOGIN":
            raise UpstreamError

    env = await _env(hook=hook)

    await check_tick(env.deps)

    assert await env.state() == "watching"
    assert await env.kinds() == []


# --- 毎分と21時の違い -----------------------------------------------------------


async def test_the_tick_uses_one_session_and_the_nightly_check_races_several() -> None:
    tick_env = await _env()
    await check_tick(tick_env.deps)
    nightly_env = await _env()
    await nightly_check(nightly_env.deps)

    assert len(tick_env.site.clients) == 1 + 1  # 商品ページ用の共有 + 1セッション
    assert len(nightly_env.site.clients) == 1 + 3


# --- 取り残し -----------------------------------------------------------------


async def test_a_stale_purchasing_favorite_becomes_unknown_and_is_never_bought_again() -> None:
    env = await _env()
    await env.repos.favorites.delete("f1")
    await env.favorite(state="purchasing", changed=NOW - timedelta(minutes=30))

    await check_tick(env.deps)

    assert await env.state() == "unknown"
    assert await env.kinds() == ["unknown"]
    assert env.site.order_posts == 0


async def test_a_recent_purchasing_favorite_is_left_alone() -> None:
    env = await _env()
    await env.repos.favorites.delete("f1")
    await env.favorite(state="purchasing", changed=NOW - timedelta(minutes=1))

    await check_tick(env.deps)

    assert await env.state() == "purchasing"
    assert await env.kinds() == []


async def test_a_stale_purchasing_favorite_is_recovered_even_while_the_master_switch_is_off() -> (
    None
):
    env = await _env()
    await env.repos.favorites.delete("f1")
    await env.favorite(state="purchasing", changed=NOW - timedelta(minutes=30))
    await env.repos.settings.set_auto_purchase_enabled(False)

    await check_tick(env.deps)

    assert await env.state() == "unknown"
    assert await env.kinds() == ["unknown"]
    assert env.site.clients == []  # 商品ページの確認も購入もしない
