from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NamedTuple

from spider.application.ports import (
    AccountRepository,
    Clock,
    FavoriteRepository,
    KeywordFavoriteRepository,
    LoginFailed,
    NotificationRepository,
    NotPurchasable,
    PaymentMethodUnavailable,
    PreviewTimeout,
    SecretBox,
    SecretBoxError,
    SettingsRepository,
    SiteClient,
    UnsupportedPaymentMethod,
    UpstreamError,
)
from spider.application.preview import CheckoutParsers, PreviewConfig, store_pickup_preview
from spider.application.products import search_products
from spider.application.retry import PreviewRuntime, backoff_delay, fixed_delay, retrying
from spider.application.use_cases import SITE, ProductNotFound
from spider.domain.account import Notification, NotificationKind
from spider.domain.favorite import Favorite, FavoriteState
from spider.domain.keyword_favorite import KeywordFavorite
from spider.domain.product import OrderResult, ProductSummary

HEARTBEAT_INTERVAL_SECONDS = 300


class MonitorDeps(NamedTuple):
    favorites: FavoriteRepository
    accounts: AccountRepository
    notifications: NotificationRepository
    settings: SettingsRepository
    secret_box: SecretBox
    clock: Clock
    client_factory: Callable[[], SiteClient]
    extract_product_page: Callable[[str, int], ProductSummary]
    checkout_parsers: CheckoutParsers
    runtime: PreviewRuntime
    preview_config: PreviewConfig
    tick_deadline_seconds: float
    stale_purchasing_seconds: float
    nightly_parallelism: int
    nightly_retry_interval_seconds: float
    keyword_favorites: KeywordFavoriteRepository
    extract_search_results: Callable[[str, set[int]], list[ProductSummary]]
    extract_product_ids: Callable[[str], set[int]]
    new_id: Callable[[], str]


async def check_tick(deps: MonitorDeps) -> None:
    """1分ごとの監視。1セッション・短い制限時間で購入する。画面には出さない。"""
    await _run(deps, nightly=False)


async def nightly_check(deps: MonitorDeps) -> None:
    """毎晩21時（JST）の確認。混雑に備え、リトライと複数セッションの競争で購入する。"""
    await _run(deps, nightly=True)


async def _run(deps: MonitorDeps, *, nightly: bool) -> None:
    now = deps.clock.now()
    await _heartbeat(deps, now)
    active = await deps.favorites.list_active()
    # 取り残しの回収は、マスタースイッチに関係なく行う（注文が送られた可能性があり、必ず知らせる）
    for favorite in active:
        if favorite.state == "purchasing":
            await _expire_if_stale(deps, favorite, now)
    if not await deps.settings.auto_purchase_enabled():
        return  # OFF の間は、商品ページの確認も購入も検知もしない（検知のみでは何も残らないため）
    watching = [f for f in active if f.state == "watching"]
    if watching:
        client = deps.client_factory()
        try:
            for favorite in watching:
                await _check_favorite(deps, client, favorite, nightly)
        finally:
            await client.aclose()
    await _check_keyword_favorites(deps, nightly)


async def _heartbeat(deps: MonitorDeps, now: datetime) -> None:
    last = await deps.settings.last_tick_at()
    if last is None or now - last >= timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS):
        await deps.settings.record_tick(now)


async def _move(
    deps: MonitorDeps,
    favorite: Favorite,
    current: FavoriteState,
    target: FavoriteState,
    version: int,
) -> bool:
    return await deps.favorites.transition(favorite.id, current, target, version, deps.clock.now())


async def _notify(
    deps: MonitorDeps, favorite: Favorite, kind: NotificationKind, message: str
) -> None:
    await deps.notifications.add(
        Notification(
            id=deps.new_id(),
            favorite_id=favorite.id,
            kind=kind,
            message=message,
            created_at=deps.clock.now(),
            read=False,
        )
    )


async def _expire_if_stale(deps: MonitorDeps, favorite: Favorite, now: datetime) -> None:
    """購入処理中のまま止まったもの。再購入はせず、購入履歴の確認を促す。"""
    if now - favorite.state_changed_at <= timedelta(seconds=deps.stale_purchasing_seconds):
        return
    if await _move(deps, favorite, "purchasing", "unknown", favorite.state_version):
        await _notify(
            deps,
            favorite,
            "unknown",
            f"購入処理が途中で止まりました。購入履歴を確認してください"
            f"（自動では再購入しません）: {favorite.product_name}",
        )


async def _stop_with_notice(
    deps: MonitorDeps, favorite: Favorite, kind: NotificationKind, message: str
) -> None:
    """監視中のお気に入りを止めて通知する（遷移に成功した実行だけが通知する）。"""
    if await _move(deps, favorite, "watching", "stopped", favorite.state_version):
        await _notify(deps, favorite, kind, message)


async def _check_favorite(
    deps: MonitorDeps, client: SiteClient, favorite: Favorite, nightly: bool
) -> None:
    try:
        page = await client.get(f"{SITE}/product/{favorite.product_id}")
        summary = deps.extract_product_page(page, favorite.product_id)
    except UpstreamError:
        return  # 一時的なエラーは、書き込みも通知もせず次の回に任せる
    except ProductNotFound:
        await _stop_with_notice(
            deps,
            favorite,
            "rejected",
            f"商品が見つからないため、監視を停止しました: {favorite.product_name}",
        )
        return
    if not summary.in_stock:
        return

    if not deps.preview_config.allow_order_submit:
        await _stop_with_notice(
            deps,
            favorite,
            "submit_disabled",
            f"購入可能になりましたが、注文確定が無効のため購入せず、監視を停止しました"
            f": {favorite.product_name}",
        )
        return
    cap = favorite.price_cap_yen
    if cap is not None and summary.price_yen > cap:
        await _stop_with_notice(
            deps,
            favorite,
            "skipped_price_cap",
            f"価格 {summary.price_yen:,}円が上限 {cap:,}円を超えているため購入せず、"
            f"監視を停止しました: {favorite.product_name}",
        )
        return
    # 条件付き遷移に成功した実行だけが購入する（毎分の監視と21時が重なっても1回）
    if not await _move(deps, favorite, "watching", "purchasing", favorite.state_version):
        return
    await _purchase(deps, favorite, favorite.state_version + 1, nightly)


async def _stop_account(deps: MonitorDeps, favorite: Favorite, version: int, label: str) -> None:
    """ロック防止のため、そのアカウントのお気に入りをすべて止める。"""
    await _move(deps, favorite, "purchasing", "stopped", version)
    stopped = 1
    for other in await deps.favorites.list_all(favorite.account_id):
        if other.id != favorite.id and other.state == "watching":
            if await _move(deps, other, "watching", "stopped", other.state_version):
                stopped += 1
    await _notify(
        deps,
        favorite,
        "account_stopped",
        f"{label}のログインに失敗したため、監視を停止しました（{stopped}件）。"
        "パスワードを確認して、アカウントを再登録してください。",
    )


async def _purchase(deps: MonitorDeps, favorite: Favorite, version: int, nightly: bool) -> None:
    found = await deps.accounts.get_with_secret(favorite.account_id)
    if found is None:
        await _stop_account(deps, favorite, version, f"アカウント（{favorite.account_id}）の")
        return
    account, encrypted = found
    try:
        password = deps.secret_box.decrypt(encrypted)
    except SecretBoxError:
        await _stop_account(deps, favorite, version, f"{account.label}の資格情報を復号できず、")
        return

    config = deps.preview_config
    if nightly:
        config = config._replace(parallelism=deps.nightly_parallelism)
        retry_delay = fixed_delay(deps.nightly_retry_interval_seconds)
    else:
        config = config._replace(parallelism=1, deadline_seconds=deps.tick_deadline_seconds)
        retry_delay = backoff_delay
    try:
        result = await store_pickup_preview(
            client_factory=deps.client_factory,
            parsers=deps.checkout_parsers,
            config=config,
            runtime=deps.runtime,
            email=account.email,
            password=password,
            product_id=favorite.product_id,
            payment_method_id=favorite.payment_method,
            submit_order=True,
            retry_delay=retry_delay,
        )
    except LoginFailed:
        await _stop_account(deps, favorite, version, f"{account.label}の")
        return
    except (PreviewTimeout, UpstreamError, NotPurchasable):
        await _move(deps, favorite, "purchasing", "watching", version)  # 次の監視で再試行
        return
    except (PaymentMethodUnavailable, UnsupportedPaymentMethod, ProductNotFound):
        await _move(deps, favorite, "purchasing", "stopped", version)
        await _notify(
            deps,
            favorite,
            "rejected",
            f"支払方法が選べない、または商品が見つからないため、監視を停止しました"
            f": {favorite.product_name}",
        )
        return
    except Exception:
        # 想定外の失敗は、注文が送られた可能性を否定できないため、再購入せず unknown にする
        await _move(deps, favorite, "purchasing", "unknown", version)
        await _notify(
            deps,
            favorite,
            "unknown",
            f"購入処理で想定外のエラーが起きました。購入履歴を確認してください"
            f"（自動では再購入しません）: {favorite.product_name}",
        )
        return
    await _record(deps, favorite, version, result.order)


async def _record(
    deps: MonitorDeps, favorite: Favorite, version: int, order: OrderResult | None
) -> None:
    # 注文の結果は、状態の更新に失敗しても（実行中にお気に入りが削除されたなど）必ず通知する。
    # 注文が送られた事実をユーザーに伝えることが目的で、通知を状態の更新の成否に結び付けない。
    name = favorite.product_name
    if order is not None and order.status == "submitted":
        await _move(deps, favorite, "purchasing", "purchased", version)
        await _notify(
            deps, favorite, "purchased", f"注文が確定しました（受注番号 {order.order_id}）: {name}"
        )
    elif order is not None and order.status == "rejected":
        if order.reason == "history_unavailable":
            await _move(deps, favorite, "purchasing", "watching", version)  # 注文は送っていない
            return
        await _move(deps, favorite, "purchasing", "rejected", version)
        reason = (
            "サイトの reCAPTCHA により注文は受理されませんでした（注文は作られていません）"
            if order.reason == "recaptcha"
            else "注文は受理されませんでした（注文は作られていません）"
        )
        await _notify(deps, favorite, "rejected", f"{reason}: {name}")
    else:
        await _move(deps, favorite, "purchasing", "unknown", version)
        await _notify(
            deps,
            favorite,
            "unknown",
            f"注文の成否が不明です。購入履歴を確認してください（自動では再購入しません）: {name}",
        )


async def _check_keyword_favorites(deps: MonitorDeps, nightly: bool) -> None:
    """キーワードお気に入りの新着を検知して通知する（購入・送信はしない）。"""
    delay = fixed_delay(deps.nightly_retry_interval_seconds) if nightly else backoff_delay
    deadline = deps.preview_config.deadline_seconds if nightly else deps.tick_deadline_seconds
    for favorite in await deps.keyword_favorites.list_enabled():
        client = deps.client_factory()

        async def do_search(
            c: SiteClient = client, f: KeywordFavorite = favorite
        ) -> list[ProductSummary]:
            return await search_products(
                c, f.keyword, deps.extract_search_results, deps.extract_product_ids, f.category_id
            )

        try:
            results = await retrying(
                do_search,
                runtime=deps.runtime,
                deadline_at=deps.runtime.now() + deadline,
                delay=delay,
            )
        except (UpstreamError, PreviewTimeout):
            continue  # 一時的なエラーは、通知も seen 更新もせず次回に任せる
        finally:
            await client.aclose()
        for product in results:
            if not product.in_stock:
                continue  # 購入可能でない新着は seen に入れず持ち越す
            if not await deps.keyword_favorites.claim_product(favorite.id, product.product_id):
                continue  # すでに通知済み
            cap = favorite.price_cap_yen
            if cap is not None and product.price_yen > cap:
                await _notify_arrival(
                    deps,
                    favorite,
                    "skipped_price_cap",
                    f"新着が価格上限を超えているためスキップ: {product.name}"
                    f"（{product.price_yen:,}円 > 上限 {cap:,}円）",
                    product,
                )
            else:
                await _notify_arrival(
                    deps,
                    favorite,
                    "new_arrival",
                    f"新着あり: {product.name}（{product.price_yen:,}円・"
                    f"キーワード「{favorite.keyword}」）",
                    product,
                )
                await deps.keyword_favorites.bump_new_arrival(favorite.id)


async def _notify_arrival(
    deps: MonitorDeps,
    favorite: KeywordFavorite,
    kind: NotificationKind,
    message: str,
    product: ProductSummary,
) -> None:
    await deps.notifications.add(
        Notification(
            id=deps.new_id(),
            favorite_id=favorite.id,
            kind=kind,
            message=message,
            created_at=deps.clock.now(),
            read=False,
            product_id=product.product_id,
            payment_method=favorite.payment_method,
        )
    )
