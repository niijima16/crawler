import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from spider.application.schedule import JST
from spider.worker import Scheduler, run

pytestmark = pytest.mark.anyio


def _jst(hour: int, minute: int = 0, second: int = 0, day: int = 22) -> datetime:
    return datetime(2026, 11, day, hour, minute, second, tzinfo=JST).astimezone(UTC)


def test_the_first_call_runs_a_tick_and_then_one_per_minute() -> None:
    scheduler = Scheduler()
    start = _jst(12)

    assert scheduler.due(start) == ["tick"]
    assert scheduler.due(start + timedelta(seconds=30)) == []
    assert scheduler.due(start + timedelta(seconds=60)) == ["tick"]
    assert scheduler.due(start + timedelta(seconds=90)) == []


def test_nine_pm_runs_the_nightly_check_instead_of_the_tick() -> None:
    scheduler = Scheduler()
    scheduler.due(_jst(20, 59))

    assert scheduler.due(_jst(21, 0)) == ["nightly"]
    assert scheduler.due(_jst(21, 0, 30)) == []
    assert scheduler.due(_jst(21, 1)) == ["tick"]


def test_the_nightly_check_runs_once_a_day() -> None:
    scheduler = Scheduler()

    assert scheduler.due(_jst(21, 0)) == ["nightly"]
    assert "nightly" not in scheduler.due(_jst(21, 2))
    assert scheduler.due(_jst(21, 0, day=23)) == ["nightly"]


def test_a_late_start_does_not_catch_up_on_a_missed_nightly_check() -> None:
    scheduler = Scheduler()

    assert scheduler.due(_jst(21, 30)) == ["tick"]
    assert scheduler.due(_jst(22, 0)) == ["tick"]


async def test_the_loop_runs_the_due_actions_and_survives_errors() -> None:
    now = {"t": _jst(20, 58)}
    calls: list[str] = []

    class Clock:
        def now(self) -> datetime:
            return now["t"]

    async def sleep(seconds: float) -> None:
        now["t"] += timedelta(seconds=30)
        await asyncio.sleep(0)

    async def tick() -> None:
        calls.append("tick")
        if len(calls) == 1:
            raise RuntimeError("boom")  # 失敗してもループは続く

    async def nightly() -> None:
        calls.append("nightly")

    rounds = {"n": 0}

    def stop() -> bool:
        rounds["n"] += 1
        return rounds["n"] > 9

    await run(Scheduler(), tick=tick, nightly=nightly, clock=Clock(), sleep=sleep, stop=stop)

    assert calls == ["tick", "tick", "nightly", "tick", "tick"]
