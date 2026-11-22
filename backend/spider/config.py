from collections.abc import Mapping
from typing import NamedTuple

from spider.application.preview import MAX_PARALLELISM, PreviewConfig

DEFAULT_PARALLELISM = 3
DEFAULT_DEADLINE_SECONDS = 60.0
MAX_DEADLINE_SECONDS = 120.0
HISTORY_DEADLINE_SECONDS = 10.0
LOGIN_CHECK_DEADLINE_SECONDS = 15.0


def _bounded(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    value = float(raw)  # 数値でなければ ValueError
    if not low <= value <= high:
        raise ValueError(f"{name} は {low}〜{high} の範囲で指定してください: {raw}")
    return value


def _flag(env: Mapping[str, str], name: str) -> bool:
    raw = env.get(name, "false").strip().lower()
    if raw in {"true", "1"}:
        return True
    if raw in {"false", "0"}:
        return False
    raise ValueError(f"{name} は true / false で指定してください: {raw}")


def load_preview_config(env: Mapping[str, str]) -> PreviewConfig:
    return PreviewConfig(
        parallelism=int(
            _bounded(env, "PREVIEW_PARALLELISM", DEFAULT_PARALLELISM, 1, MAX_PARALLELISM)
        ),
        deadline_seconds=_bounded(
            env, "PREVIEW_DEADLINE_SECONDS", DEFAULT_DEADLINE_SECONDS, 1, MAX_DEADLINE_SECONDS
        ),
        history_deadline_seconds=HISTORY_DEADLINE_SECONDS,
        allow_order_submit=_flag(env, "ALLOW_ORDER_SUBMIT"),
    )


NIGHTLY_MAX_PARALLELISM = 10


class MonitorSettings(NamedTuple):
    tick_deadline_seconds: float
    stale_purchasing_seconds: float
    nightly_parallelism: int
    nightly_retry_interval_seconds: float


def load_monitor_settings(env: Mapping[str, str]) -> MonitorSettings:
    return MonitorSettings(
        tick_deadline_seconds=_bounded(env, "TICK_DEADLINE_SECONDS", 20.0, 1, MAX_DEADLINE_SECONDS),
        stale_purchasing_seconds=900.0,
        nightly_parallelism=int(
            _bounded(env, "NIGHTLY_PARALLELISM", 10, 1, NIGHTLY_MAX_PARALLELISM)
        ),
        nightly_retry_interval_seconds=_bounded(
            env, "NIGHTLY_RETRY_INTERVAL_SECONDS", 0.1, 0.05, 8
        ),
    )
