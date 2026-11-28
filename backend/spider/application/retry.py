from collections.abc import Awaitable, Callable
from typing import NamedTuple

from spider.application.ports import PreviewTimeout, UpstreamError

BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 8.0


class PreviewRuntime(NamedTuple):
    """時間まわりの注入物（テストでは偽物にする）。"""

    sleep: Callable[[float], Awaitable[None]]
    rng: Callable[[], float]
    now: Callable[[], float]


def backoff_delay(attempt: int, rng: Callable[[], float]) -> float:
    """基準1秒×2の累乗（上限8秒）に、0.5〜1.0倍のゆらぎを掛けた待ち時間。"""
    return min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2.0**attempt) * (0.5 + 0.5 * rng())


def fixed_delay(base: float) -> Callable[[int, Callable[[], float]], float]:
    """attempt に依らない固定間隔（base の 0.5〜1.5 倍のゆらぎ）。待ち時間が伸びない。"""

    def delay(attempt: int, rng: Callable[[], float]) -> float:
        return base * (0.5 + rng())

    return delay


def jitter_delay(max_seconds: float) -> Callable[[int, Callable[[], float]], float]:
    """0〜max_seconds のランダムな待ち。attempt に依らず延びない（自動の引き継ぎで粘るとき用）。"""

    def delay(attempt: int, rng: Callable[[], float]) -> float:
        return rng() * max_seconds

    return delay


async def retrying[T](
    step: Callable[[], Awaitable[T]],
    *,
    runtime: PreviewRuntime,
    deadline_at: float,
    on_attempt: Callable[[], None] | None = None,
    delay: Callable[[int, Callable[[], float]], float] = backoff_delay,
) -> T:
    """一時的エラー（UpstreamError）だけを、制限時間までバックオフしてリトライする。"""
    attempt = 0
    while True:
        if on_attempt is not None:
            on_attempt()
        try:
            return await step()
        except UpstreamError:
            wait = delay(attempt, runtime.rng)
            if runtime.now() + wait >= deadline_at:
                raise PreviewTimeout from None
            await runtime.sleep(wait)
            attempt += 1
