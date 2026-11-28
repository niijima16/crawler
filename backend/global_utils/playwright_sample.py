"""拡張（browser-extension/）が開いた確認画面に、起動済みの Chrome へ CDP で接続して処理する。

事前準備（1回だけ）:
  1. 専用プロファイルで、リモートデバッグを有効にして Chrome を起動する
     （Chrome 136 以降は既定プロファイルではリモートデバッグが効かないため、--user-data-dir が必要）
       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         --remote-debugging-port=9222 --user-data-dir="$HOME/.pickup-chrome"
  2. その Chrome に browser-extension/ を読み込む（README 参照）
使い方:
  このスクリプトを起動したままにする → ツール画面で「確認画面を開く」。
  拡張が確認画面のタブを開くたびに、そのタブを1回だけ処理する。終了は Ctrl+C。
"""
import re
import time
from playwright.sync_api import Browser, Playwright, sync_playwright, expect, Locator, Page
from human_cursor import SyncHumanCursor

DRY_RUN = True          # True ならボタンの手前で止まる。本番で押すときだけ False にする
TIMEOUT = 10_000        # 要素を待つ時間（ミリ秒）
CDP_URL = "http://localhost:9222"
CONFIRM_URL = "https://www.dollyteria.com/cart/confirm"
READY_TIMEOUT = 90_000  # 503 の自動リロード（拡張側で最大約1分）を待つ時間（ミリ秒）


def try_human_click(cursor: SyncHumanCursor, loc: Locator) -> bool:
    """人間らしい動きでクリックを試す。成功すれば True、失敗すれば False を返す"""
    try:
        loc.wait_for(state="visible", timeout=TIMEOUT)
        loc.scroll_into_view_if_needed()   # 画面の外にある要素だと座標がずれるため
        cursor.click(loc)
        return True
    except Exception as e:
        print(f"[warn] cursor.click 失敗: {e!r}")
        return False


def check_agree(page: Page, cursor: SyncHumanCursor) -> None:
    agree = page.get_by_role("checkbox", name="同意する")
    if agree.is_checked():
        return

    # 1. チェックボックス本体 → 2. ラベル の順に、マウスの動きを付けてクリックを試す
    for target in (agree, page.get_by_text("同意する", exact=True)):
        if try_human_click(cursor, target):
            try:
                expect(agree).to_be_checked(timeout=3_000)
                return
            except AssertionError:
                print("[warn] クリックしたがチェックが入らなかった")

    # 3. 最後の手段として Playwright 標準の check を使う（隠れた input にも効く）
    print("[warn] フォールバック: agree.check(force=True)")
    agree.check(force=True)
    expect(agree).to_be_checked()

def click_buy(page: Page, cursor: SyncHumanCursor) -> None:
    buy = page.get_by_role("button", name="購入する")
    expect(buy).to_be_enabled(timeout=TIMEOUT)

    if DRY_RUN:
        print("[info] DRY_RUN のため購入ボタンは押さない")
        return

    confirm_url = page.url
    try_human_click(cursor, buy)

    # 購入ボタンはむやみに押し直さない（二重注文を防ぐため）。
    # 画面が変わったかを確認し、「明らかにまだ押されていない」ときだけ1回だけ標準の click で押し直す
    try:
        page.wait_for_url(lambda url: url != confirm_url, timeout=TIMEOUT)
        return
    except Exception:
        pass

    if page.url == confirm_url and buy.is_visible() and buy.is_enabled():
        print("[warn] 画面が変わらないため、標準の click で1回だけ押し直す")
        buy.click()
        page.wait_for_url(lambda url: url != confirm_url, timeout=TIMEOUT)
    else:
        raise RuntimeError("購入後の状態がわからない。二重注文の恐れがあるので手動で確認してください")



def wait_confirm_page(browser: Browser, handled: set[Page]) -> Page:
    """拡張が開いた確認画面のタブのうち、まだ処理していないものが現れるまで待って返す"""
    while True:
        for context in browser.contexts:
            for page in context.pages:
                if page.url.startswith(CONFIRM_URL) and page not in handled:
                    return page
        time.sleep(0.5)


def process_page(page: Page) -> None:
    """1つのタブを処理する。失敗しても例外は出さず、調査用のファイルを残して次のタブを待てるようにする"""
    context = page.context
    context.tracing.start(screenshots=True, snapshots=True)   # 失敗したときの調査用
    page.set_default_timeout(TIMEOUT)
    cursor = SyncHumanCursor(page)

    try:
        # 混雑時は拡張がリロードを繰り返すので、同意チェックが出るまで待つ
        page.get_by_role("checkbox", name="同意する").wait_for(timeout=READY_TIMEOUT)
        check_agree(page, cursor)
        click_buy(page, cursor)
        print("[ok] 完了:", page.url)
    except Exception as e:
        context.tracing.stop(path="trace.zip")
        try:
            page.screenshot(path="error.png", full_page=True)
        except Exception as shot_err:  # タブが閉じられたときなど
            print(f"[warn] error.png を保存できなかった: {shot_err!r}")
        print(f"[error] {e!r}")
        print("[error] error.png / trace.zip を保存した。次のタブを待ちます")
    else:
        context.tracing.stop()


def run(playwright: Playwright) -> None:
    # 自分で起動せず、拡張が入った起動済みの Chrome に接続する
    browser = playwright.chromium.connect_over_cdp(CDP_URL)
    handled: set[Page] = set()
    try:
        while True:
            print("[info] 拡張が確認画面を開くのを待っています…（終了は Ctrl+C）")
            page = wait_confirm_page(browser, handled)
            handled.add(page)
            process_page(page)
    finally:
        browser.close()   # CDP 接続では切断だけ（ユーザーの Chrome とタブは閉じない）


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)