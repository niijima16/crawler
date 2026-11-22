import pytest

from spider.application.ports import LoginFailed, PreviewTimeout, UpstreamError
from spider.application.retry import PreviewRuntime, backoff_delay, retrying

pytestmark = pytest.mark.anyio


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_backoff_doubles_and_is_capped_at_eight_seconds() -> None:
    assert [backoff_delay(n, lambda: 1.0) for n in range(6)] == [1, 2, 4, 8, 8, 8]


def test_backoff_jitter_is_between_half_and_full() -> None:
    assert backoff_delay(2, lambda: 0.0) == 2.0
    assert backoff_delay(2, lambda: 0.5) == 3.0
    assert backoff_delay(2, lambda: 1.0) == 4.0


async def test_retries_upstream_errors_then_succeeds() -> None:
    clock = FakeTime()
    calls = 0

    async def step() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise UpstreamError
        return "ok"

    result = await retrying(
        step, runtime=PreviewRuntime(clock.sleep, lambda: 1.0, clock), deadline_at=60
    )

    assert result == "ok"
    assert clock.sleeps == [1.0, 2.0]


async def test_non_transient_errors_are_not_retried() -> None:
    clock = FakeTime()

    async def step() -> str:
        raise LoginFailed

    with pytest.raises(LoginFailed):
        await retrying(
            step, runtime=PreviewRuntime(clock.sleep, lambda: 1.0, clock), deadline_at=60
        )

    assert clock.sleeps == []


async def test_gives_up_with_timeout_when_the_deadline_would_be_exceeded() -> None:
    clock = FakeTime()

    async def step() -> str:
        raise UpstreamError

    with pytest.raises(PreviewTimeout):
        await retrying(
            step, runtime=PreviewRuntime(clock.sleep, lambda: 1.0, clock), deadline_at=10
        )

    assert clock.now < 10


async def test_counts_every_attempt() -> None:
    clock = FakeTime()
    attempts = 0

    def on_attempt() -> None:
        nonlocal attempts
        attempts += 1

    calls = 0

    async def step() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise UpstreamError
        return "ok"

    await retrying(
        step,
        runtime=PreviewRuntime(clock.sleep, lambda: 1.0, clock),
        deadline_at=60,
        on_attempt=on_attempt,
    )

    assert attempts == 2
