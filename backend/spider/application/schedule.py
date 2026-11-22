from datetime import datetime, time, timedelta, timezone

JST = timezone(timedelta(hours=9), "JST")  # 日本にサマータイムは無いため、固定のオフセットで足りる
NIGHTLY_AT = time(21, 0)


def next_nightly(now: datetime) -> datetime:
    """次の毎晩21時（JST）。ちょうど21時のときは翌日。"""
    local = now.astimezone(JST)
    candidate = datetime.combine(local.date(), NIGHTLY_AT, tzinfo=JST)
    return candidate if candidate > local else candidate + timedelta(days=1)
