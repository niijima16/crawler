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


async def retrying[T](
    step: Callable[[], Awaitable[T]],
    *,
    runtime: PreviewRuntime,
    deadline_at: float,
    on_attempt: Callable[[], None] | None = None,
) -> T:
    """一時的エラー（UpstreamError）だけを、制限時間までバックオフしてリトライする。"""
    attempt = 0
    while True:
        if on_attempt is not None:
            on_attempt()
        try:
            return await step()
        except UpstreamError:
            delay = backoff_delay(attempt, runtime.rng)
            if runtime.now() + delay >= deadline_at:
                raise PreviewTimeout from None
            await runtime.sleep(delay)
            attempt += 1
