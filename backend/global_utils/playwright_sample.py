import re
from playwright.sync_api import Playwright, sync_playwright, expect, Locator, Page
from human_cursor import SyncHumanCursor

DRY_RUN = True          # True なら購入ボタンの手前で止まる。本番で押すときだけ False にする
TIMEOUT = 10_000        # 要素を待つ時間（ミリ秒）


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


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(channel="chrome", headless=False)
    context = browser.new_context()
    context.tracing.start(screenshots=True, snapshots=True)   # 失敗したときの調査用
    page = context.new_page()
    page.set_default_timeout(TIMEOUT)
    cursor = SyncHumanCursor(page)

    try:
        page.goto("https://www.dollyteria.com/cart/confirm", wait_until="domcontentloaded")
        check_agree(page, cursor)
        click_buy(page, cursor)
        print("[ok] 完了:", page.url)
    except Exception:
        page.screenshot(path="error.png", full_page=True)
        context.tracing.stop(path="trace.zip")
        print("[error] error.png / trace.zip を保存した")
        raise
    else:
        context.tracing.stop()
    finally:
        context.close()
        browser.close()


with sync_playwright() as playwright:
    run(playwright)