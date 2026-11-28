"""引き継いだ確認画面に、ホストの Chrome（CDP）経由で同意チェックを入れる。購入ボタンは押さない。

Chrome は `--remote-debugging-port=9222 --user-data-dir=...` で起動しておく。
コンテナからは host.docker.internal で届くが、Chrome は Host ヘッダーが localhost（か IP）で
ないと拒否するため、Host を localhost:<port> にして接続する。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx
from human_cursor import HumanCursor
from playwright.async_api import Browser, Error, Page, async_playwright, expect

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.1
TAB_POLLS = 1500  # 最大150秒（引き継ぎの制限時間 最大120秒 ＋ 拡張がタブを開くまで）
READY_TIMEOUT_MS = 90_000  # 503 の自動リロード（拡張側で最大約1分）を待つ
CONFIRM_SELECTOR = 'input[name="go-next"]'


def websocket_url(ws_from_chrome: str, cdp_url: str) -> str:
    """Chrome が返す ws URL（Host に合わせて localhost になる）を、設定した接続先に向け直す。"""
    return urlsplit(ws_from_chrome)._replace(netloc=urlsplit(cdp_url).netloc).geturl()


def _confirm_pages(browser: Browser, confirm_url: str) -> list[Page]:
    return [
        page
        for context in browser.contexts
        for page in context.pages
        if page.url.startswith(confirm_url)
    ]


async def wait_new_confirm_page(
    browser: Browser,
    existing: set[Page],
    confirm_url: str,
    *,
    sleep: Callable[[float], Awaitable[None]],
    polls: int,
) -> Page:
    """接続時にはなかった確認画面のタブが現れるまで待つ。"""
    for _ in range(polls):
        for page in _confirm_pages(browser, confirm_url):
            if page not in existing:
                return page
        await sleep(POLL_SECONDS)
    raise TimeoutError("確認画面のタブが開かれなかった")


async def _check_agree(page: Page) -> None:
    agree = page.locator("#policy_agree")  # 拡張（confirm.js）と同じ見つけ方
    await agree.wait_for(timeout=READY_TIMEOUT_MS)
    if await agree.is_checked():
        return
    try:
        await agree.scroll_into_view_if_needed()  # 画面外だと座標がずれるため
        # 動きは残しつつ、待ち・ためらいをなくして速くする（既定: 速度1.75、待ち 50/50/30ms）
        await HumanCursor(page).click(
            agree, move_speed=5.0, move_delay=0, hesitate=0, wait_for_click=0
        )
    except (Error, ValueError):  # ValueError: 要素の位置が取れない（HumanCursor）
        logger.warning("マウス操作でのクリックに失敗した")
    if not await agree.is_checked():
        logger.warning("チェックが入らなかったため、check で入れる")
        await agree.check(force=True)


async def _click_button(page: Page) -> None:
    confirm = page.locator(CONFIRM_SELECTOR)
    await confirm.wait_for(timeout=READY_TIMEOUT_MS)
    # 同意チェック後に有効になるボタンだと、押しても無反応になるため待つ
    await expect(confirm).to_be_enabled(timeout=READY_TIMEOUT_MS)

    url_before = page.url
    clicked = False
    try:
        await confirm.scroll_into_view_if_needed()
        await HumanCursor(page).click(
            confirm, move_speed=5.0, move_delay=0, hesitate=0, wait_for_click=0
        )
        clicked = True
    except (Error, ValueError):
        logger.warning("マウス操作でのクリックに失敗した")

    if not clicked:
        # 位置が取れずに押せなかったときだけ、通常の click で押す
        await confirm.click()

    # 送信されたかはページ遷移で確かめる
    try:
        await page.wait_for_url(lambda u: u != url_before, timeout=READY_TIMEOUT_MS)
    except Error:
        logger.warning("確定後にページが変わらなかった（送信されていない可能性）")
        raise


class CdpConsentAssistant:
    def __init__(self, cdp_url: str) -> None:
        self._cdp_url = cdp_url.rstrip("/")
        self._host_header = f"localhost:{urlsplit(cdp_url).port}"

    async def assist(self, confirm_url: str) -> None:
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.get(
                f"{self._cdp_url}/json/version", headers={"Host": self._host_header}
            )
            response.raise_for_status()
        ws = websocket_url(response.json()["webSocketDebuggerUrl"], self._cdp_url)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(
                ws, headers={"Host": self._host_header}
            )
            try:
                existing = set(_confirm_pages(browser, confirm_url))
                page = await wait_new_confirm_page(
                    browser, existing, confirm_url, sleep=asyncio.sleep, polls=TAB_POLLS
                )
                await _check_agree(page)
                logger.info("確認画面に同意チェックを入れた")
                await _click_button(page)
                logger.info("確認画面の確定ボタンを押した")
            finally:
                await browser.close()  # CDP 接続では切断だけ（ユーザーの Chrome とタブは閉じない）
