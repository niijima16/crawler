import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { saveAutoOpen } from "./autoOpen";
import {
  ACCOUNT,
  ACCOUNT_B,
  favorite,
  GENRES,
  keywordFavorite,
  MAME,
  METHODS,
  NOTE_NEW_ARRIVAL,
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
    "GET /api/genres": () => json(200, GENRES),
    "GET /api/keyword-favorites": () => json(200, []),
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

    expect(screen.getAllByText("t***@dollyteria").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "検索" })).toBeEnabled();
  });

  it("registers the first account, unlocks, and never keeps the password", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { calls } = api({ "POST /api/accounts": () => json(200, ACCOUNT) }, []);
    render(<App />);
    await screen.findByLabelText("パスワード");

    await user.type(screen.getByLabelText("メールアドレス"), "tester@dollyteria");
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

    await waitFor(() => expect(screen.queryByText("s***@dollyteria")).not.toBeInTheDocument());
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
    [409, { detail: "not_purchasable" }, /この商品はできません/],
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
    expect(await screen.findByRole("tab", { name: /自動/ })).toHaveTextContent("2");
  });

  it("shows the favorites of the account in the favorites tab", async () => {
    api({ "GET /api/favorites": () => json(200, [favorite({ price_cap_yen: 1500 })]) });
    await ready();

    await user.click(screen.getByRole("tab", { name: "お気に入り" }));

    const tab = await screen.findByRole("region", { name: "商品お気に入り" });
    expect(tab).toHaveTextContent("SD/豆本 S-26-11-01-584-TO-ZS");
    expect(tab).toHaveTextContent("価格上限: 1,500円");
  });

  it("shows the status and the results in the auto-purchase tab", async () => {
    api({ "GET /api/notifications": () => json(200, { unread: 1, items: [NOTE_REJECTED] }) });
    await ready();

    await user.click(screen.getByRole("tab", { name: /自動/ }));

    const tab = await screen.findByRole("region", { name: "自動" });
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

type SseListener = (event: { data: string }) => void;

class FakeEventSource {
  static last: FakeEventSource | null = null;
  listeners: Record<string, SseListener> = {};
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, cb: SseListener) {
    this.listeners[type] = cb;
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    act(() => this.listeners[type]?.({ data: JSON.stringify(data) }));
  }
}

describe("browser handoff (progress stream)", () => {
  const HANDOFF = {
    cookie_name: "PHPSESSID",
    cookie_value: "sess-xyz",
    confirm_url: "https://www.dollyteria.com/cart/confirm",
  };

  beforeEach(() => {
    FakeEventSource.last = null;
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete document.documentElement.dataset.pickupExtension;
  });

  async function toHandoffMode() {
    await user.click(screen.getByRole("radio", { name: "ブラウザで" }));
  }

  function captureHandoffEvents(): CustomEvent[] {
    const events: CustomEvent[] = [];
    window.addEventListener("pickup-handoff", (e) => events.push(e as CustomEvent));
    return events;
  }

  async function startFromSearch() {
    await ready();
    await searchAndSelect();
    await toHandoffMode();
    await user.click(
      within(summary()).getByRole("button", { name: "確認画面まで進めてブラウザに引き継ぐ" }),
    );
    return (await screen.findByRole("region", { name: "確認画面への引き継ぎ" })) as HTMLElement;
  }

  it("opens the progress stream for the selected product and shows steps", async () => {
    api();
    const region = await startFromSearch();

    const source = FakeEventSource.last as FakeEventSource;
    expect(source.url).toContain("/api/store-pickup-preview/stream");
    expect(source.url).toContain("product_id=807736");
    source.emit("step", { step: "login", status: "done", attempt: 1 });
    expect(within(region).getByText("ログイン").closest("li")).toHaveClass("done");
  });

  it("opens the confirmation once on done when the extension is present", async () => {
    document.documentElement.dataset.pickupExtension = "1";
    api();
    await startFromSearch();
    const events = captureHandoffEvents();

    (FakeEventSource.last as FakeEventSource).emit("done", HANDOFF);

    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ cookieValue: "sess-xyz" });
  });

  it("does not dispatch and tells the user to install the extension when missing", async () => {
    api();
    const region = await startFromSearch();
    const events = captureHandoffEvents();

    (FakeEventSource.last as FakeEventSource).emit("done", HANDOFF);

    expect(events).toHaveLength(0);
    expect(region).toHaveTextContent("拡張機能を入れると");
  });
});

describe("keyword favorites", () => {
  const HANDOFF = {
    cookie_name: "PHPSESSID",
    cookie_value: "sess-xyz",
    confirm_url: "https://www.dollyteria.com/cart/confirm",
  };

  beforeEach(() => {
    FakeEventSource.last = null;
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete document.documentElement.dataset.pickupExtension;
  });

  it("lists keyword favorites of the account in the favorites tab", async () => {
    const { calls } = api({ "GET /api/keyword-favorites": () => json(200, [keywordFavorite()]) });
    await ready();
    await waitFor(() =>
      expect(calls.some((c) => c.key === "GET /api/keyword-favorites")).toBe(true),
    );

    await user.click(screen.getByRole("tab", { name: "お気に入り" }));

    const section = await screen.findByRole("region", { name: "キーワードお気に入り" });
    await waitFor(() => expect(section).toHaveTextContent("「豆本」"));
    expect(section).toHaveTextContent("SuperDollfie > 本体");
  });

  it("registers a keyword favorite with the chosen genre", async () => {
    const { calls } = api({ "POST /api/keyword-favorites": () => json(200, keywordFavorite()) });
    await ready();
    await user.click(screen.getByRole("tab", { name: "お気に入り" }));

    const form = await screen.findByRole("region", { name: "キーワードお気に入りを登録" });
    await within(form).findByRole("option", { name: "SDGIRL/SD13GIRL" });
    await user.type(within(form).getByLabelText("キーワード"), "豆本");
    await user.selectOptions(within(form).getByRole("combobox", { name: "ジャンル" }), "136");
    await user.click(within(form).getByRole("button", { name: "登録する" }));

    await waitFor(() =>
      expect(calls.some((c) => c.key === "POST /api/keyword-favorites")).toBe(true),
    );
    expect(calls.find((c) => c.key === "POST /api/keyword-favorites")?.body).toMatchObject({
      account_id: "a1",
      keyword: "豆本",
      category_id: 136,
    });
  });

  it("streams the handoff for a new-arrival notification and opens the confirmation", async () => {
    document.documentElement.dataset.pickupExtension = "1";
    api({
      "GET /api/notifications": () => json(200, { unread: 1, items: [NOTE_NEW_ARRIVAL] }),
    });
    await ready();
    await user.click(screen.getByRole("tab", { name: /自動/ }));

    const events: CustomEvent[] = [];
    const listener = (e: Event) => events.push(e as CustomEvent);
    window.addEventListener("pickup-handoff", listener);
    await user.click(await screen.findByRole("button", { name: "確認画面を開く" }));

    // 進捗オーバーレイが開き、その商品のストリームを購読する
    await screen.findByRole("region", { name: "確認画面への引き継ぎ" });
    const source = FakeEventSource.last as FakeEventSource;
    expect(source.url).toContain("product_id=815572");
    expect(source.url).toContain("payment_method=8");

    source.emit("done", HANDOFF);
    await waitFor(() => expect(events).toHaveLength(1));
    window.removeEventListener("pickup-handoff", listener);
    expect(events[0].detail).toEqual({ cookieValue: "sess-xyz" });
  });
});

describe("auto open on new arrivals", () => {
  const HANDOFF = {
    cookie_name: "PHPSESSID",
    cookie_value: "sess-xyz",
    confirm_url: "https://www.dollyteria.com/cart/confirm",
  };
  const arrival = (id: string, productId: number, createdAt: string, message: string) => ({
    ...NOTE_NEW_ARRIVAL,
    id,
    product_id: productId,
    created_at: createdAt,
    message,
  });
  const FIRST = arrival("n10", 111, "2026-11-25T12:00:00Z", "新着: 一つ目");
  const SECOND = arrival("n11", 222, "2026-11-25T12:00:01Z", "新着: 二つ目");

  let items: (typeof FIRST)[] = [];

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(Math, "random").mockReturnValue(1); // やり直しの待ち = 500ms
    FakeEventSource.last = null;
    vi.stubGlobal("EventSource", FakeEventSource);
    items = [];
    api({
      "GET /api/notifications": () => json(200, { unread: items.length, items }),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
    delete document.documentElement.dataset.pickupExtension;
  });

  const source = () => FakeEventSource.last as FakeEventSource;
  const tick = (ms = 1_000) => act(() => vi.advanceTimersByTimeAsync(ms));
  const dialog = () => screen.queryByRole("region", { name: "確認画面への引き継ぎ" });
  const line = () => screen.getByRole("region", { name: "自動" });

  async function arrive(...notes: (typeof FIRST)[]) {
    items = [...notes, ...items];
    await tick();
  }

  // スイッチ ON で画面を開き、「自動」タブを表示して、一つ目の自動の引き継ぎが始まるまで進める
  async function startAutoOnAutoTab() {
    saveAutoOpen(true);
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: /自動/ }));
    await arrive(FIRST);
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    return source();
  }

  const turnSwitchOff = async () =>
    fireEvent.click(await screen.findByRole("switch", { name: "新着通知で自動で確認画面を開く" }));

  it("opens the newest new arrival automatically when the switch is on", async () => {
    saveAutoOpen(true);
    await ready();

    await arrive(FIRST);

    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    expect(source().url).toContain("product_id=111");
    expect(source().url).toContain("auto=true");
  });

  it("does nothing when the switch is off", async () => {
    await ready();

    await arrive(FIRST);
    await tick();

    expect(FakeEventSource.last).toBeNull();
  });

  it("also opens an unread new arrival that is already there when the page opens", async () => {
    saveAutoOpen(true);
    items = [FIRST];
    await ready();

    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    expect(source().url).toContain("product_id=111");
  });

  it("runs an auto handoff without the progress dialog and shows one line instead", async () => {
    await startAutoOnAutoTab();

    expect(dialog()).toBeNull();
    expect(line()).toHaveTextContent("自動: 新着: 一つ目 を引き継ぎ中");
  });

  it("shows the reached confirmation in the line when nothing is queued", async () => {
    document.documentElement.dataset.pickupExtension = "1";
    const first = await startAutoOnAutoTab();

    first.emit("done", HANDOFF);

    await waitFor(() =>
      expect(line()).toHaveTextContent("自動: 新着: 一つ目 の確認画面を開きました"),
    );
    expect(dialog()).toBeNull();
  });

  it("opens the next right after reaching the confirmation, without closing anything", async () => {
    const first = await startAutoOnAutoTab();
    await arrive(SECOND);
    expect(source()).toBe(first); // 実行中は次を開かない
    expect(line()).toHaveTextContent("順番待ち 1件");

    first.emit("done", HANDOFF);

    await waitFor(() => expect(source()).not.toBe(first));
    expect(source().url).toContain("product_id=222");
    expect(line()).toHaveTextContent("自動: 新着: 二つ目 を引き継ぎ中");
  });

  it("opens the next right after a sell-out", async () => {
    const first = await startAutoOnAutoTab();
    await arrive(SECOND);

    first.emit("error", { reason: "not_purchasable" });

    await waitFor(() => expect(source()).not.toBe(first));
    expect(source().url).toContain("product_id=222");
  });

  it("says it was sold out when nothing is queued", async () => {
    const first = await startAutoOnAutoTab();

    first.emit("error", { reason: "not_purchasable" });

    await waitFor(() => expect(line()).toHaveTextContent("自動: 新着: 一つ目 は売り切れでした"));
  });

  it("says the confirmation could not be opened without the extension", async () => {
    // テスト環境に拡張は無い
    const first = await startAutoOnAutoTab();

    first.emit("done", HANDOFF);

    await waitFor(() =>
      expect(line()).toHaveTextContent(
        "自動: 新着: 一つ目 の確認画面を開けませんでした（拡張機能が入っていません）",
      ),
    );
  });

  it("locks the manual open button while an auto handoff runs", async () => {
    const first = await startAutoOnAutoTab();

    expect(within(line()).getByRole("button", { name: "確認画面を開く" })).toBeDisabled();

    first.emit("error", { reason: "login_failed" });
    await waitFor(() =>
      expect(within(line()).getByRole("button", { name: "確認画面を開く" })).toBeEnabled(),
    );
  });

  it("does not restart when the login fails and says it failed", async () => {
    const first = await startAutoOnAutoTab();

    first.emit("error", { reason: "login_failed" });
    await tick(1_000);

    expect(source()).toBe(first);
    expect(line()).toHaveTextContent("自動: 新着: 一つ目 の引き継ぎに失敗しました（login_failed）");
    expect(dialog()).toBeNull();
  });

  it("restarts a busy auto handoff again and again until it ends otherwise", async () => {
    await startAutoOnAutoTab();

    for (const reason of ["timeout", "upstream_error", "timeout", "timeout"]) {
      const before = source();
      before.emit("error", { reason });
      await tick(500);
      await waitFor(() => expect(source()).not.toBe(before));
      expect(source().url).toContain("product_id=111");
      expect(source().url).toContain("auto=true");
    }
    expect(line()).toHaveTextContent("（混雑のためやり直し 5回目）");
    expect(dialog()).toBeNull();
  });

  it("does not restart a manual handoff and shows its dialog", async () => {
    items = [FIRST];
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: /自動/ }));
    fireEvent.click(await screen.findByRole("button", { name: "確認画面を開く" }));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());
    const manual = source();
    expect(dialog()).not.toBeNull();

    manual.emit("error", { reason: "timeout" });
    await tick(1_000);

    expect(source()).toBe(manual);
  });

  it("turning the switch off stops the running auto handoff, empties the queue and clears the line", async () => {
    const first = await startAutoOnAutoTab();
    await arrive(SECOND);

    await turnSwitchOff();
    await tick();

    expect(first.closed).toBe(true);
    expect(source()).toBe(first); // 次も開かない
    expect(line()).not.toHaveTextContent("自動:");
  });

  it("turning the switch off while waiting to restart stops the restart", async () => {
    const first = await startAutoOnAutoTab();

    first.emit("error", { reason: "timeout" });
    await turnSwitchOff();
    await tick(1_000);

    expect(source()).toBe(first);
  });

  it("refreshes the unread count right after marking all as read", async () => {
    let unread = 1;
    api({
      "GET /api/notifications": () => json(200, { unread, items: [FIRST] }),
      "POST /api/notifications/read": () => {
        unread = 0;
        return json(200, { unread: 0 });
      },
    });
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: /自動/ }));
    await screen.findByText("未読 1");

    fireEvent.click(screen.getByRole("button", { name: "すべて既読にする" }));

    // 1秒ごとの取得を待たずに反映する（タイマーは進めない）
    await waitFor(() => expect(screen.queryByText("未読 1")).toBeNull(), { timeout: 500 });
  });
});
