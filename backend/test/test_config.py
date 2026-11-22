import pytest

from spider.application.preview import PreviewConfig
from spider.config import MonitorSettings, load_monitor_settings, load_preview_config


def test_defaults_are_safe() -> None:
    assert load_preview_config({}) == PreviewConfig(
        parallelism=3,
        deadline_seconds=60.0,
        history_deadline_seconds=10.0,
        allow_order_submit=False,
    )


def test_values_are_read_from_the_environment() -> None:
    config = load_preview_config(
        {
            "PREVIEW_PARALLELISM": "5",
            "PREVIEW_DEADLINE_SECONDS": "120",
            "ALLOW_ORDER_SUBMIT": "true",
        }
    )

    assert config.parallelism == 5
    assert config.deadline_seconds == 120.0
    assert config.allow_order_submit is True


@pytest.mark.parametrize(
    "env",
    [
        {"PREVIEW_PARALLELISM": "0"},
        {"PREVIEW_PARALLELISM": "6"},
        {"PREVIEW_PARALLELISM": "many"},
        {"PREVIEW_DEADLINE_SECONDS": "0"},
        {"PREVIEW_DEADLINE_SECONDS": "121"},
        {"ALLOW_ORDER_SUBMIT": "maybe"},
    ],
)
def test_out_of_range_or_invalid_values_fail_at_startup(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        load_preview_config(env)


def test_monitor_settings_defaults_and_bounds() -> None:
    assert load_monitor_settings({}) == MonitorSettings(20.0, 900.0)
    assert load_monitor_settings({"TICK_DEADLINE_SECONDS": "30"}).tick_deadline_seconds == 30.0
    with pytest.raises(ValueError):
        load_monitor_settings({"TICK_DEADLINE_SECONDS": "0"})
