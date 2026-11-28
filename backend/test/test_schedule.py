from datetime import UTC, datetime

from spider.application.schedule import JST, next_nightly


def _jst(hour: int, minute: int = 0, day: int = 22) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=JST)


def test_before_nine_pm_it_is_today() -> None:
    assert next_nightly(_jst(20, 59)) == _jst(21)


def test_at_nine_pm_it_is_tomorrow() -> None:
    assert next_nightly(_jst(21)) == _jst(21, day=23)


def test_after_nine_pm_it_is_tomorrow() -> None:
    assert next_nightly(_jst(23, 30)) == _jst(21, day=23)


def test_utc_input_is_converted_to_jst() -> None:
    # 2026-11-22 11:30 UTC は JST で 20:30
    assert next_nightly(datetime(2026, 11, 22, 11, 30, tzinfo=UTC)) == _jst(21)
    # 2026-11-22 12:30 UTC は JST で 21:30 → 翌日
    assert next_nightly(datetime(2026, 11, 22, 12, 30, tzinfo=UTC)) == _jst(21, day=23)
