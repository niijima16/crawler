"""ローカル用のワーカー。1分ごとの監視と、毎晩21時（JST）の確認を、同じユースケースで動かす。

AWS では、このユースケース（check_tick / nightly_check）を EventBridge Scheduler → Lambda から呼ぶ。
"""

import asyncio
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Literal, Protocol

from spider.application.monitor import MonitorDeps, check_tick, nightly_check
from spider.application.preview import CheckoutParsers
from spider.application.retry import PreviewRuntime
from spider.application.schedule import JST, NIGHTLY_AT
from spider.config import load_monitor_settings, load_preview_config
from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.http_client import HttpSiteClient
from spider.infrastructure.product_parsers import (
    extract_confirm,
    extract_order_form,
    extract_payment_options,
    extract_product_page,
    is_in_cart,
    is_recaptcha_rejected,
)
from spider.wiring import SystemClock, build_store, new_id

TICK_INTERVAL = timedelta(seconds=60)
NIGHTLY_WINDOW = timedelta(minutes=5)  # 21:00〜21:05 に起動していれば実行する。取りこぼしは補わない

log = logging.getLogger("spider.worker")
Action = Literal["tick", "nightly"]


class WallClock(Protocol):
    def now(self) -> datetime: ...


class Scheduler:
    def __init__(self) -> None:
        self._last_tick: datetime | None = None
        self._nightly_day: date | None = None

    def due(self, now: datetime) -> list[Action]:
        local = now.astimezone(JST)
        window_start = datetime.combine(local.date(), NIGHTLY_AT, tzinfo=JST)
        if (
            window_start <= local < window_start + NIGHTLY_WINDOW
            and self._nightly_day != local.date()
        ):
            self._nightly_day = local.date()
            self._last_tick = now
            return ["nightly"]
        if self._last_tick is None or now - self._last_tick >= TICK_INTERVAL:
            self._last_tick = now
            return ["tick"]
        return []


async def run(
    scheduler: Scheduler,
    *,
    tick: Callable[[], Awaitable[None]],
    nightly: Callable[[], Awaitable[None]],
    clock: WallClock,
    sleep: Callable[[float], Awaitable[None]],
    stop: Callable[[], bool] = lambda: False,
) -> None:
    while not stop():
        for action in scheduler.due(clock.now()):
            try:
                await (tick if action == "tick" else nightly)()
            except Exception:
                log.exception(
                    "%s failed", action
                )  # 失敗してもループは続ける（資格情報は出力しない）
        await sleep(1.0)


def build_monitor_deps(
    env: Mapping[str, str],
) -> tuple[MonitorDeps, Callable[[], Awaitable[None]]]:
    store, setup = build_store(env)
    settings = load_monitor_settings(env)
    runtime = PreviewRuntime(sleep=asyncio.sleep, rng=random.random, now=time.monotonic)
    deps = MonitorDeps(
        favorites=store.favorites,
        accounts=store.accounts,
        notifications=store.notifications,
        settings=store.settings,
        secret_box=store.secret_box,
        clock=SystemClock(),
        client_factory=HttpSiteClient,
        extract_product_page=extract_product_page,
        checkout_parsers=CheckoutParsers(
            is_in_cart=is_in_cart,
            payment_options=extract_payment_options,
            confirm=extract_confirm,
            order_form=extract_order_form,
            recaptcha_rejected=is_recaptcha_rejected,
            order_ids=lambda html: {o.order_id for o in extract_orders(html)},
        ),
        runtime=runtime,
        preview_config=load_preview_config(env),
        tick_deadline_seconds=settings.tick_deadline_seconds,
        stale_purchasing_seconds=settings.stale_purchasing_seconds,
        nightly_parallelism=settings.nightly_parallelism,
        nightly_retry_interval_seconds=settings.nightly_retry_interval_seconds,
        new_id=new_id,
    )
    return deps, setup


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    deps, setup = build_monitor_deps(os.environ)
    await setup()
    log.info("worker started: tick every 60s, nightly check at 21:00 JST")
    await run(
        Scheduler(),
        tick=lambda: check_tick(deps),
        nightly=lambda: nightly_check(deps),
        clock=SystemClock(),
        sleep=asyncio.sleep,
    )


if __name__ == "__main__":
    asyncio.run(main())
