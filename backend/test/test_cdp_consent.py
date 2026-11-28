import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from spider.infrastructure import cdp_consent
from spider.infrastructure.cdp_consent import wait_new_confirm_page, websocket_url

CONFIRM = "https://www.dollyteria.com/cart/confirm"


def test_websocket_url_points_to_the_configured_host() -> None:
    url = websocket_url(
        "ws://localhost:9222/devtools/browser/abc", "http://host.docker.internal:9222"
    )

    assert url == "ws://host.docker.internal:9222/devtools/browser/abc"


class _Page:
    """本物の Page と同じく、ハッシュ可能（set に入る）"""

    def __init__(self, url: str) -> None:
        self.url = url


async def _no_sleep(_: float) -> None:
    return None


def _browser(*pages: _Page) -> Any:
    return cast(Any, SimpleNamespace(contexts=[SimpleNamespace(pages=list(pages))]))


def test_wait_new_confirm_page_skips_existing_and_other_tabs() -> None:
    old = _Page(CONFIRM)
    other = _Page("https://www.dollyteria.com/cart")
    new = _Page(CONFIRM)

    page = asyncio.run(
        wait_new_confirm_page(
            _browser(old, other, new), {cast(Any, old)}, CONFIRM, sleep=_no_sleep, polls=3
        )
    )

    assert page is cast(Any, new)


def test_wait_new_confirm_page_gives_up_after_polls() -> None:
    old = _Page(CONFIRM)

    with pytest.raises(TimeoutError):
        asyncio.run(
            wait_new_confirm_page(
                _browser(old), {cast(Any, old)}, CONFIRM, sleep=_no_sleep, polls=3
            )
        )


class _Checkbox:
    def __init__(self) -> None:
        self.checked = False
        self.forced = False

    async def wait_for(self, **_: Any) -> None:
        return None

    async def is_checked(self) -> bool:
        return self.checked

    async def scroll_into_view_if_needed(self) -> None:
        return None

    async def check(self, force: bool = False) -> None:
        self.checked = True
        self.forced = force


class _ConfirmPage:
    def __init__(self) -> None:
        self.checkbox = _Checkbox()
        self.selectors: list[str] = []

    def locator(self, selector: str) -> _Checkbox:
        self.selectors.append(selector)
        return self.checkbox


class _NoBoxCursor:
    """要素の位置が取れないときの HumanCursor（ValueError を出す）"""

    def __init__(self, page: Any) -> None:
        pass

    async def click(self, target: Any, **_: Any) -> None:
        raise ValueError("Element has no bounding box")


def test_check_agree_finds_policy_agree_and_falls_back_when_cursor_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cdp_consent, "HumanCursor", _NoBoxCursor)
    page = _ConfirmPage()

    asyncio.run(cdp_consent._check_agree(cast(Any, page)))

    assert page.selectors == ["#policy_agree"]
    assert page.checkbox.checked and page.checkbox.forced


class _RecordingCursor:
    """クリックに渡されたオプションを記録する HumanCursor"""

    options: dict[str, Any] = {}

    def __init__(self, page: Any) -> None:
        self._page = page

    async def click(self, target: Any, **options: Any) -> None:
        _RecordingCursor.options = options
        await target.check()


def test_check_agree_clicks_without_human_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cdp_consent, "HumanCursor", _RecordingCursor)
    page = _ConfirmPage()

    asyncio.run(cdp_consent._check_agree(cast(Any, page)))

    options = _RecordingCursor.options
    assert options["move_delay"] == 0 and options["hesitate"] == 0
    assert options["wait_for_click"] == 0
    assert options["move_speed"] > 1.75  # 既定より速く
    assert page.checkbox.checked and not page.checkbox.forced  # マウス操作で入った
