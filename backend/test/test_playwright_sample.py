from types import SimpleNamespace
from typing import Any, cast

import pytest

from global_utils import playwright_sample

CONFIRM = playwright_sample.CONFIRM_URL


class _Page:
    """本物の Page と同じく、ハッシュ可能（set に入る）"""

    def __init__(self, url: str) -> None:
        self.url = url


def test_wait_confirm_page_skips_handled_and_other_urls() -> None:
    handled = _Page(CONFIRM)
    other = _Page("https://www.dollyteria.com/cart")
    fresh = _Page(CONFIRM + "?x=1")
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[handled, other, fresh])])

    page = playwright_sample.wait_confirm_page(cast(Any, browser), {cast(Any, handled)})

    assert page is fresh


class _FailingPage:
    """同意チェックが現れずに失敗する確認画面"""

    url = CONFIRM

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.context = SimpleNamespace(
            tracing=SimpleNamespace(
                start=lambda **_: None,
                stop=lambda path=None: self.calls.append(f"trace:{path}"),
            )
        )

    def set_default_timeout(self, _: int) -> None:
        pass

    def get_by_role(self, *_: Any, **__: Any) -> SimpleNamespace:
        def wait_for(**_: Any) -> None:
            raise TimeoutError("同意チェックが出ない")

        return SimpleNamespace(wait_for=wait_for)

    def screenshot(self, path: str, **_: Any) -> None:
        self.calls.append(f"screenshot:{path}")


def test_process_page_swallows_error_and_saves_screenshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(playwright_sample, "SyncHumanCursor", lambda page: None)
    page = _FailingPage()

    playwright_sample.process_page(cast(Any, page))  # 例外を外に出さない

    assert page.calls == ["trace:trace.zip", "screenshot:error.png"]


class _ClosedPage(_FailingPage):
    """処理中にタブが閉じられ、スクリーンショットも撮れない確認画面"""

    def screenshot(self, path: str, **_: Any) -> None:
        raise RuntimeError("Target page has been closed")


def test_process_page_survives_closed_tab_and_saves_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(playwright_sample, "SyncHumanCursor", lambda page: None)
    page = _ClosedPage()

    playwright_sample.process_page(cast(Any, page))  # 例外を外に出さない

    assert page.calls == ["trace:trace.zip"]
