import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { favorite, METHODS } from "../test-data";
import { json, mockApi } from "../test-utils";
import { FavoritesTab } from "./FavoritesTab";

const user = userEvent.setup();

function setup(favorites = [favorite()]) {
  const onChanged = vi.fn();
  render(<FavoritesTab favorites={favorites} methods={METHODS} onChanged={onChanged} />);
  return { onChanged, tab: screen.getByRole("region", { name: "お気に入り" }) };
}

afterEach(() => vi.unstubAllGlobals());

describe("FavoritesTab", () => {
  it("shows an empty state", () => {
    const { tab } = setup([]);

    expect(tab).toHaveTextContent("お気に入りはまだありません");
    expect(tab).toHaveTextContent("0 / 20 件");
  });

  it("lists the favorites with their settings and the watching count", () => {
    const { tab } = setup([
      favorite({ id: "f1", price_cap_yen: 1500 }),
      favorite({
        id: "f2",
        product_id: 2,
        product_name: "別の商品",
        payment_method: "3",
        state: "stopped",
      }),
    ]);

    expect(tab).toHaveTextContent("監視中 1 / 全 2 件（上限 20）");
    expect(tab).toHaveTextContent("SD/豆本 S-26-11-01-584-TO-ZS");
    expect(tab).toHaveTextContent("支払方法: 店頭支払");
    expect(tab).toHaveTextContent("価格上限: 1,500円");
    expect(tab).toHaveTextContent("支払方法: 代金引換");
    expect(tab).toHaveTextContent("価格上限: なし");
  });

  it.each([
    ["watching", "監視中"],
    ["purchasing", "購入処理中"],
    ["purchased", "購入済み"],
    ["rejected", "受理されず"],
    ["unknown", "成否不明"],
    ["stopped", "停止"],
  ] as const)("labels the %s state", (state, label) => {
    const { tab } = setup([favorite({ state })]);

    expect(within(tab).getByText(label, { selector: ".st" })).toBeInTheDocument();
  });

  it("removes a favorite", async () => {
    const { calls } = mockApi({
      "DELETE /api/favorites/f1": () => new Response(null, { status: 204 }),
    });
    const { tab, onChanged } = setup();

    await user.click(within(tab).getByRole("button", { name: "解除" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls[0].key).toBe("DELETE /api/favorites/f1");
  });

  it.each(["stopped", "rejected", "unknown", "purchased"] as const)(
    "lets the user resume a %s favorite",
    async (state) => {
      const { calls } = mockApi({ "PATCH /api/favorites/f1": () => json(200, favorite()) });
      const { tab, onChanged } = setup([favorite({ state })]);

      await user.click(within(tab).getByRole("button", { name: "再開" }));

      await waitFor(() => expect(onChanged).toHaveBeenCalled());
      expect(calls[0].body).toEqual({ resume: true });
    },
  );

  it("does not offer to remove or resume a favorite that is being purchased", () => {
    const { tab } = setup([favorite({ state: "purchasing" })]);

    expect(within(tab).getByRole("button", { name: "解除" })).toBeDisabled();
    expect(within(tab).queryByRole("button", { name: "再開" })).not.toBeInTheDocument();
  });

  it("edits the payment method and the price cap, and can clear the cap", async () => {
    const { calls } = mockApi({ "PATCH /api/favorites/f1": () => json(200, favorite()) });
    const { tab, onChanged } = setup([favorite({ price_cap_yen: 1500 })]);

    await user.click(within(tab).getByRole("button", { name: "編集" }));
    const select = within(tab).getByRole("combobox", { name: "支払方法" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["店頭支払", "代金引換", "銀行振込", "郵便振替"]);
    await user.selectOptions(select, "1");
    const cap = within(tab).getByLabelText("価格上限（円）");
    await user.clear(cap);
    await user.click(within(tab).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls[0].body).toEqual({ payment_method: "1", price_cap_yen: null });
  });

  it("shows an error when a change is rejected", async () => {
    mockApi({ "DELETE /api/favorites/f1": () => json(502, { detail: "x" }) });
    const { tab } = setup();

    await user.click(within(tab).getByRole("button", { name: "解除" }));

    expect(await within(tab).findByText(/サイトに接続できません/)).toBeInTheDocument();
  });
});
