import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Handoff } from "../types";
import { HandoffCard } from "./HandoffCard";

const user = userEvent.setup();

const HANDOFF: Handoff = {
  cookie_name: "PHPSESSID",
  cookie_value: "sess-secret-123",
  confirm_url: "https://www.dollyteria.com/cart/confirm",
};

const PREVIEW = {
  product_id: 769926,
  item_name: "SD16/OF:靴 U-26-07-22-192-TN-ZU",
  payment_method: "店頭支払",
  shipping_fee_yen: 660,
  total_yen: 3740,
};

function setup(extensionInstalled: boolean) {
  render(
    <HandoffCard preview={PREVIEW} handoff={HANDOFF} extensionInstalled={extensionInstalled} />,
  );
  return { card: screen.getByRole("region", { name: "ブラウザで購入する" }) };
}

afterEach(() => vi.restoreAllMocks());

describe("HandoffCard", () => {
  it("shows the confirmation summary and says the final click is manual", () => {
    const { card } = setup(true);

    expect(card).toHaveTextContent("SD16/OF:靴 U-26-07-22-192-TN-ZU");
    expect(card).toHaveTextContent("3,740円");
    expect(card).toHaveTextContent("購入する");
    expect(card).toHaveTextContent("ブラウザで自分で押");
  });

  it("points to the open button and shows no fallback when the extension is present", () => {
    const { card } = setup(true);

    expect(card).toHaveTextContent("確認画面を開く");
    expect(within(card).queryByText(/DevTools/)).not.toBeInTheDocument();
  });

  it("explains the extension and the DevTools fallback when it is missing", () => {
    const { card } = setup(false);

    expect(card).toHaveTextContent("拡張");
    expect(card).toHaveTextContent("DevTools");
    expect(card).toHaveTextContent("PHPSESSID");
  });

  it("keeps the session value hidden until revealed and never stores it", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { card } = setup(false);

    expect(card).not.toHaveTextContent("sess-secret-123");
    await user.click(within(card).getByRole("button", { name: "表示" }));
    expect(card).toHaveTextContent("sess-secret-123");

    expect(setItem).not.toHaveBeenCalled();
  });

  it("warns that it is a live session", () => {
    const { card } = setup(true);

    expect(card).toHaveTextContent("生きたセッション");
  });
});
