import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import {
  ACCOUNT,
  ACCOUNT_B,
  favorite,
  MAME,
  METHODS,
  NOTE_REJECTED,
  PREVIEW_RESULT,
  SOLD_OUT,
  STATUS,
} from "./test-data";
import { json, mockApi } from "./test-utils";
import type { Favorite } from "./types";

const user = userEvent.setup();

type Routes = Parameters<typeof mockApi>[0];

function api(extra: Routes = {}, accounts = [ACCOUNT]) {
  return mockApi({
    "GET /api/payment-methods": () => json(200, METHODS),
    "GET /api/accounts": () => json(200, accounts),
    "GET /api/favorites": () => json(200, []),
    "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
    "GET /api/auto-purchase/status": () => json(200, STATUS),
    "GET /api/products": () => json(200, [MAME, SOLD_OUT]),
    "GET /api/products/807736": () => json(200, MAME),
    "POST /api/store-pickup-preview": () => json(200, PREVIEW_RESULT),
    ...extra,
  });
}

async function ready() {
  render(<App />);
  await screen.findByText("使用中");
}

async function searchAndSelect() {
  await user.click(screen.getByRole("radio", { name: "部分一致" }));
  await user.type(screen.getByRole("textbox", { name: "検索語" }), "豆本");
  await user.click(screen.getByRole("button", { name: "検索" }));
  const cards = await screen.findAllByRole("button", { name: "この商品を選ぶ" });
  await user.click(cards[0]);
}

const summary = () => screen.getByRole("region", { name: "ご注文内容" });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("account gate", () => {
  it("locks the options, search and run cards until an account is available", async () => {
    api({}, []);
    render(<App />);

    expect(await screen.findByLabelText("パスワード")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "検索" })).toBeDisabled();
    expect(await screen.findByRole("combobox", { name: "支払方法" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "確認画面まで進める" })).toBeDisabled();
    expect(screen.getAllByText(/ログインすると使えます/).length).toBeGreaterThan(0);
  });

  it("uses the first saved account and unlocks", async () => {
    api();
    await ready();

    expect(screen.getAllByText("t***@example.com").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "検索" })).toBeEnabled();
  });

  it("registers the first account, unlocks, and never keeps the password", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { calls } = api({ "POST /api/accounts": () => json(200, ACCOUNT) }, []);
    render(<App />);
    await screen.findByLabelText("パスワード");

    await user.type(screen.getByLabelText("メールアドレス"), "tester@example.com");
    await user.type(screen.getByLabelText("パスワード"), "secret-pw");
    await user.click(screen.getByRole("button", { name: "ログインを確認して追加" }));

    await screen.findByText("使用中");
    expect(screen.getByRole("button", { name: "検索" })).toBeEnabled();
    expect(setItem).not.toHaveBeenCalled();
    const others = calls.filter((c) => c.key !== "POST /api/accounts");
    expect(JSON.stringify(others)).not.toContain("secret-pw");
  });

  it("loads the favorites of the account that is switched to", async () => {
    const { calls } = api({}, [ACCOUNT, ACCOUNT_B]);
    await ready();

    await user.click(screen.getByRole("button", { name: "切り替える" }));

    await waitFor(() =>
      expect(
        calls
          .filter((c) => c.key === "GET /api/favorites")
          .map((c) => c.url.searchParams.get("account_id")),
      ).toEqual(["a1", "a2"]),
    );
  });

  it("removes another account", async () => {
    api({ "DELETE /api/accounts/a2": () => new Response(null, { status: 204 }) }, [
      ACCOUNT,
      ACCOUNT_B,
    ]);
    await ready();

    await user.click(screen.getByRole("button", { name: "削除" }));
    await user.click(screen.getByRole("button", { name: "削除する" }));

    await waitFor(() => expect(screen.queryByText("s***@example.com")).not.toBeInTheDocument());
  });
});

describe("search", () => {
  it("searches by partial match and shows product cards with stock", async () => {
    const { calls } = api();
    await ready();

    await user.click(screen.getByRole("radio", { name: "部分一致" }));
    await user.type(screen.getByRole("textbox", { name: "検索語" }), "豆本");
    await user.click(screen.getByRole("button", { name: "検索" }));

    expect(await screen.findByText(MAME.name)).toBeInTheDocument();
    expect(screen.getByText("在庫なし")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "GET /api/products")?.url.searchParams.get("keyword")).toBe(
      "豆本",
    );
  });

  it("searches by code, accepting a pasted path", async () => {
    const { calls } = api();
    await ready();

    await user.type(screen.getByRole("textbox", { name: "検索語" }), "product/807736");
    await user.click(screen.getByRole("button", { name: "検索" }));

    expect(await screen.findByText(MAME.name)).toBeInTheDocument();
    expect(calls.some((c) => c.key === "GET /api/products/807736")).toBe(true);
  });

  it("rejects an invalid code without calling the API", async () => {
    const { calls } = api();
    await ready();

    await user.type(screen.getByRole("textbox", { name: "検索語" }), "abc");
    await user.click(screen.getByRole("button", { name: "検索" }));

    expect(await screen.findByText(/商品コードの数字を入力してください/)).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("GET /api/products"))).toBe(false);
  });

  it("explains a missing product and an empty result", async () => {
    api({
      "GET /api/products/1": () => json(404, { detail: "product not found" }),
      "GET /api/products": () => json(200, []),
    });
    await ready();

    await user.type(screen.getByRole("textbox", { name: "検索語" }), "1");
    await user.click(screen.getByRole("button", { name: "検索" }));
    expect(await screen.findByText(/その商品は見つかりません/)).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "部分一致" }));
    await user.clear(screen.getByRole("textbox", { name: "検索語" }));
    await user.type(screen.getByRole("textbox", { name: "検索語" }), "zzz");
    await user.click(screen.getByRole("button", { name: "検索" }));
    expect(await screen.findByText(/見つかりませんでした/)).toBeInTheDocument();
  });
});

describe("running the flow", () => {
  it("runs with the saved account and shows the confirmation result", async () => {
    const { calls } = api();
    await ready();

    expect(summary()).toHaveTextContent("商品を選ぶと");
    await searchAndSelect();
    expect(summary()).toHaveTextContent(MAME.name);
    expect(summary()).toHaveTextContent("990円");
    expect(summary()).toHaveTextContent("店頭支払");

    await user.click(within(summary()).getByRole("button", { name: "確認画面まで進める" }));

    const result = await screen.findByRole("region", { name: "結果" });
    expect(result).toHaveTextContent("確認画面まで進めました");
    expect(result).toHaveTextContent("1,650円");
    expect(result).toHaveTextContent("7 回");
    expect(calls.find((c) => c.key === "POST /api/store-pickup-preview")?.body).toEqual({
      account_id: "a1",
      product_id: 807736,
      payment_method: "8",
      submit_order: false,
      handoff: false,
    });
  });

  it("sends the selected payment method", async () => {
    const { calls } = api();
    await ready();
    await searchAndSelect();

    await user.selectOptions(screen.getByRole("combobox", { name: "支払方法" }), "3");
    await user.click(within(summary()).getByRole("button", { name: "確認画面まで進める" }));

    await screen.findByText(/確認画面まで進めました/);
    expect(calls.find((c) => c.key === "POST /api/store-pickup-preview")?.body).toMatchObject({
      payment_method: "3",
    });
  });

  it("disables the options and the button while running", async () => {
    let finish: () => void = () => {};
    api({
      "POST /api/store-pickup-preview": () =>
        new Promise<Response>((resolve) => {
          finish = () => resolve(json(200, PREVIEW_RESULT));
        }),
    });
    await ready();
    await searchAndSelect();

    await user.click(within(summary()).getByRole("button", { name: "確認画面まで進める" }));

    expect(await screen.findByText(/サイトに接続しています/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "支払方法" })).toBeDisabled();
    expect(within(summary()).getByRole("button", { name: "確認画面まで進める" })).toBeDisabled();
    finish();
    await screen.findByText(/確認画面まで進めました/);
  });

  it.each([
    [409, { detail: "not_purchasable" }, /この商品は購入できません/],
    [409, { detail: "payment_method_unavailable" }, /選んだ支払方法は、この商品では選べません/],
    [504, { detail: "timed out" }, /時間内に確認画面へ進めませんでした/],
    [404, { detail: "product not found" }, /商品が見つかりません/],
    [502, { detail: "upstream request failed" }, /サイトに接続できません/],
  ])("explains a %s error", async (status, body, message) => {
    api({ "POST /api/store-pickup-preview": () => json(status, body) });
    await ready();
    await searchAndSelect();

    await user.click(within(summary()).getByRole("button", { name: "確認画面まで進める" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("tells the user to re-register the account when its login is rejected", async () => {
    api({ "POST /api/store-pickup-preview": () => json(401, { detail: "login failed" }) });
    await ready();
    await searchAndSelect();

    await user.click(within(summary()).getByRole("button", { name: "確認画面まで進める" }));

    expect(await screen.findByText(/ログイン情報が無効になりました/)).toBeInTheDocument();
  });
});

describe("order mode", () => {
  async function toOrderMode() {
    await user.click(screen.getByRole("radio", { name: "注文確定まで" }));
  }

  it("is off by default and does not ask for confirmation", async () => {
    const { calls } = api();
    await ready();
    await searchAndSelect();

    expect(screen.getByRole("radio", { name: "確認画面まで" })).toBeChecked();
    await user.click(within(summary()).getByRole("button", { name: "確認画面まで進める" }));

    await screen.findByText(/確認画面まで進めました/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /api/store-pickup-preview")?.body).toMatchObject({
      submit_order: false,
    });
  });

  it("asks for confirmation and sends nothing until the user confirms", async () => {
    const { calls } = api({
      "POST /api/store-pickup-preview": () =>
        json(200, {
          ...PREVIEW_RESULT,
          order: { status: "submitted", order_id: "96301", reason: null },
        }),
    });
    await ready();
    await searchAndSelect();
    await toOrderMode();

    await user.click(within(summary()).getByRole("button", { name: "注文確定まで実行する" }));

    const dialog = screen.getByRole("dialog");
    expect(calls.some((c) => c.key === "POST /api/store-pickup-preview")).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "注文確定まで実行する" }));

    expect(await screen.findByText(/注文が確定しました/)).toBeInTheDocument();
    expect(screen.getByText(/96301/)).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /api/store-pickup-preview")?.body).toMatchObject({
      submit_order: true,
    });
  });

  it("does not send anything when the dialog is cancelled", async () => {
    const { calls } = api();
    await ready();
    await searchAndSelect();
    await toOrderMode();

    await user.click(within(summary()).getByRole("button", { name: "注文確定まで実行する" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "キャンセル" }),
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.some((c) => c.key === "POST /api/store-pickup-preview")).toBe(false);
  });

  it.each([
    [{ status: "rejected", order_id: null, reason: "recaptcha" }, /注文は受理されませんでした/],
    [{ status: "unknown", order_id: null, reason: "no_response" }, /注文の成否が不明です/],
  ])("explains the order result %j", async (order, message) => {
    api({ "POST /api/store-pickup-preview": () => json(200, { ...PREVIEW_RESULT, order }) });
    await ready();
    await searchAndSelect();
    await toOrderMode();

    await user.click(within(summary()).getByRole("button", { name: "注文確定まで実行する" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "注文確定まで実行する" }),
    );

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("falls back to the confirmation-only mode when a preview-only payment method is chosen", async () => {
    api();
    await ready();
    await toOrderMode();

    await user.selectOptions(screen.getByRole("combobox", { name: "支払方法" }), "10000006");

    expect(screen.getByRole("radio", { name: "確認画面まで" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "注文確定まで" })).toBeDisabled();
  });

  it("explains that order submission is disabled on the server", async () => {
    api({
      "POST /api/store-pickup-preview": () => json(403, { detail: "order submission is disabled" }),
    });
    await ready();
    await searchAndSelect();
    await toOrderMode();

    await user.click(within(summary()).getByRole("button", { name: "注文確定まで実行する" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "注文確定まで実行する" }),
    );

    expect(await screen.findByText(/注文確定は無効になっています/)).toBeInTheDocument();
  });
});

describe("tabs and favorites", () => {
  it("shows the search tab first and the unread count on the auto-purchase tab", async () => {
    api({ "GET /api/notifications": () => json(200, { unread: 2, items: [NOTE_REJECTED] }) });
    await ready();

    expect(screen.getByRole("tab", { name: "商品を探す" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await screen.findByRole("tab", { name: /自動購入/ })).toHaveTextContent("2");
  });

  it("shows the favorites of the account in the favorites tab", async () => {
    api({ "GET /api/favorites": () => json(200, [favorite({ price_cap_yen: 1500 })]) });
    await ready();

    await user.click(screen.getByRole("tab", { name: "お気に入り" }));

    const tab = await screen.findByRole("region", { name: "お気に入り" });
    expect(tab).toHaveTextContent("SD/豆本 S-26-11-01-584-TO-ZS");
    expect(tab).toHaveTextContent("価格上限: 1,500円");
  });

  it("shows the status and the results in the auto-purchase tab", async () => {
    api({ "GET /api/notifications": () => json(200, { unread: 1, items: [NOTE_REJECTED] }) });
    await ready();

    await user.click(screen.getByRole("tab", { name: /自動購入/ }));

    const tab = await screen.findByRole("region", { name: "自動購入" });
    await waitFor(() =>
      expect(tab).toHaveTextContent("reCAPTCHA により注文は受理されませんでした"),
    );
    expect(tab).toHaveTextContent("稼働状態");
  });

  it("registers a favorite after the user consents, with the chosen payment method", async () => {
    let list: Favorite[] = [];
    const { calls } = api({
      "GET /api/favorites": () => json(200, list),
      "POST /api/favorites": () => {
        list = [favorite()];
        return json(200, list[0]);
      },
    });
    await ready();
    await user.click(screen.getByRole("radio", { name: "部分一致" }));
    await user.type(screen.getByRole("textbox", { name: "検索語" }), "豆本");
    await user.click(screen.getByRole("button", { name: "検索" }));
    await screen.findByText(MAME.name);

    await user.click(screen.getAllByRole("button", { name: "お気に入りに登録" })[0]);
    expect(screen.getByText(/自動で注文確定まで進みます/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "登録する" }));

    expect(await screen.findByRole("button", { name: "お気に入り済み" })).toBeDisabled();
    expect(calls.find((c) => c.key === "POST /api/favorites")?.body).toEqual({
      account_id: "a1",
      product_id: MAME.product_id,
      payment_method: "8",
    });
  });

  it("explains a duplicate favorite", async () => {
    api({ "POST /api/favorites": () => json(409, { detail: "duplicate_favorite" }) });
    await ready();
    await user.click(screen.getByRole("radio", { name: "部分一致" }));
    await user.type(screen.getByRole("textbox", { name: "検索語" }), "豆本");
    await user.click(screen.getByRole("button", { name: "検索" }));
    await screen.findByText(MAME.name);

    await user.click(screen.getAllByRole("button", { name: "お気に入りに登録" })[0]);
    await user.click(screen.getByRole("button", { name: "登録する" }));

    expect(await screen.findByText(/すでにお気に入りに入っています/)).toBeInTheDocument();
  });

  it("cannot register a favorite with a payment method that cannot complete an order", async () => {
    api();
    await ready();
    await user.selectOptions(screen.getByRole("combobox", { name: "支払方法" }), "10000006");
    await user.click(screen.getByRole("radio", { name: "部分一致" }));
    await user.type(screen.getByRole("textbox", { name: "検索語" }), "豆本");
    await user.click(screen.getByRole("button", { name: "検索" }));
    await screen.findByText(MAME.name);

    for (const star of screen.getAllByRole("button", { name: "お気に入りに登録" })) {
      expect(star).toBeDisabled();
    }
  });
});

describe("browser handoff", () => {
  const HANDOFF = {
    cookie_name: "PHPSESSID",
    cookie_value: "sess-xyz",
    confirm_url: "https://www.dollyteria.com/cart/confirm",
  };

  async function toHandoffMode() {
    await user.click(screen.getByRole("radio", { name: "ブラウザで購入" }));
  }

  function captureHandoffEvents(): CustomEvent[] {
    const events: CustomEvent[] = [];
    window.addEventListener("pickup-handoff", (e) => events.push(e as CustomEvent));
    return events;
  }

  afterEach(() => {
    delete document.documentElement.dataset.pickupExtension;
  });

  it("sends handoff=true and shows the handoff card", async () => {
    const { calls } = api({
      "POST /api/store-pickup-preview": () => json(200, { ...PREVIEW_RESULT, handoff: HANDOFF }),
    });
    await ready();
    await searchAndSelect();
    await toHandoffMode();

    await user.click(
      within(summary()).getByRole("button", { name: "確認画面まで進めてブラウザに引き継ぐ" }),
    );

    const card = await screen.findByRole("region", { name: "ブラウザで購入する" });
    expect(card).toHaveTextContent("SD/豆本 S-26-11-01-584-TO-ZS");
    const body = calls.find((c) => c.key === "POST /api/store-pickup-preview")?.body;
    expect(body).toMatchObject({ handoff: true, submit_order: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("auto-opens the confirmation once when the extension is present", async () => {
    document.documentElement.dataset.pickupExtension = "1";
    api({
      "POST /api/store-pickup-preview": () => json(200, { ...PREVIEW_RESULT, handoff: HANDOFF }),
    });
    await ready();
    await searchAndSelect();
    await toHandoffMode();
    const events = captureHandoffEvents();

    await user.click(
      within(summary()).getByRole("button", { name: "確認画面まで進めてブラウザに引き継ぐ" }),
    );
    await screen.findByRole("region", { name: "ブラウザで購入する" });

    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ cookieValue: "sess-xyz" });
  });

  it("does not auto-open when the extension is missing", async () => {
    api({
      "POST /api/store-pickup-preview": () => json(200, { ...PREVIEW_RESULT, handoff: HANDOFF }),
    });
    await ready();
    await searchAndSelect();
    await toHandoffMode();
    const events = captureHandoffEvents();

    await user.click(
      within(summary()).getByRole("button", { name: "確認画面まで進めてブラウザに引き継ぐ" }),
    );
    await screen.findByRole("region", { name: "ブラウザで購入する" });

    expect(events).toHaveLength(0);
    expect(within(summary()).getByRole("button", { name: "確認画面を開く" })).toBeDisabled();
    expect(screen.getAllByText(/DevTools/).length).toBeGreaterThan(0);
  });

  it("re-opens the confirmation from the button (extension present)", async () => {
    document.documentElement.dataset.pickupExtension = "1";
    api({
      "POST /api/store-pickup-preview": () => json(200, { ...PREVIEW_RESULT, handoff: HANDOFF }),
    });
    await ready();
    await searchAndSelect();
    await toHandoffMode();

    await user.click(
      within(summary()).getByRole("button", { name: "確認画面まで進めてブラウザに引き継ぐ" }),
    );
    await screen.findByRole("region", { name: "ブラウザで購入する" });

    const events = captureHandoffEvents();
    await user.click(within(summary()).getByRole("button", { name: "確認画面を開く" }));

    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ cookieValue: "sess-xyz" });
  });
});
