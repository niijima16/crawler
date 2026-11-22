import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { METHODS } from "../test-data";
import { OptionsCard } from "./OptionsCard";

function setup(props: Partial<Parameters<typeof OptionsCard>[0]> = {}) {
  const handlers = { onPayment: vi.fn(), onMode: vi.fn(), onSearchMode: vi.fn() };
  render(
    <OptionsCard
      methods={METHODS}
      paymentId="8"
      mode="check"
      searchMode="code"
      disabled={false}
      {...handlers}
      {...props}
    />,
  );
  return { ...handlers, card: screen.getByRole("region", { name: "オプション" }) };
}

describe("OptionsCard", () => {
  it("collects every selection in one place", () => {
    const { card } = setup();

    expect(within(card).getByRole("radiogroup", { name: "実行モード" })).toBeInTheDocument();
    expect(within(card).getByRole("combobox", { name: "支払方法" })).toBeInTheDocument();
    expect(within(card).getByRole("radiogroup", { name: "検索方式" })).toBeInTheDocument();
  });

  it("offers three execution modes", () => {
    const { card } = setup();
    const group = within(card).getByRole("radiogroup", { name: "実行モード" });

    expect(within(group).getAllByRole("radio")).toHaveLength(3);
    for (const name of ["確認画面まで", "注文確定まで", "ブラウザで購入"]) {
      expect(within(group).getByRole("radio", { name })).toBeInTheDocument();
    }
  });

  it("lets ブラウザで購入 be chosen for a non-card method", async () => {
    const { card, onMode } = setup();

    await userEvent.click(within(card).getByRole("radio", { name: "ブラウザで購入" }));

    expect(onMode).toHaveBeenCalledWith("handoff");
  });

  it("does not allow ブラウザで購入 for the credit card", () => {
    const { card } = setup({ paymentId: "10000028" });

    expect(within(card).getByRole("radio", { name: "ブラウザで購入" })).toBeDisabled();
  });

  it("lists all eight payment methods with store payment as the default", () => {
    const { card } = setup();
    const select = within(card).getByRole("combobox", { name: "支払方法" });

    expect(within(select).getAllByRole("option")).toHaveLength(8);
    expect(select).toHaveValue("8");
    expect(within(select).getByRole("option", { name: "後払い" })).toBeInTheDocument();
  });

  it("shows the credit card but does not let it be chosen", () => {
    const { card } = setup();

    const option = within(card).getByRole("option", { name: "クレジットカード（未対応）" });

    expect(option).toBeDisabled();
    expect(card).toHaveTextContent("ブラウザでのカード情報入力が必要なため未対応");
  });

  it("reports the chosen payment method", async () => {
    const { card, onPayment } = setup();

    await userEvent.selectOptions(within(card).getByRole("combobox", { name: "支払方法" }), "3");

    expect(onPayment).toHaveBeenCalledWith("3");
  });

  it("reports mode and search mode changes", async () => {
    const { card, onMode, onSearchMode } = setup();

    await userEvent.click(within(card).getByRole("radio", { name: "注文確定まで" }));
    await userEvent.click(within(card).getByRole("radio", { name: "部分一致" }));

    expect(onMode).toHaveBeenCalledWith("order");
    expect(onSearchMode).toHaveBeenCalledWith("partial");
  });

  it.each(["10000006", "10000050", "10000002_1"])(
    "does not allow order submission for the preview-only method %s",
    (paymentId) => {
      const { card } = setup({ paymentId });

      expect(within(card).getByRole("radio", { name: "注文確定まで" })).toBeDisabled();
      expect(card).toHaveTextContent("外部の決済・審査を伴うため");
    },
  );

  it("warns while the order mode is selected", () => {
    const { card } = setup({ mode: "order" });

    expect(card).toHaveTextContent("注文確定モード");
    expect(within(card).getByRole("radio", { name: "注文確定まで" })).toBeChecked();
  });

  it("is locked while disabled", () => {
    const { card } = setup({ disabled: true });

    for (const control of within(card).getAllByRole("radio")) expect(control).toBeDisabled();
    expect(within(card).getByRole("combobox", { name: "支払方法" })).toBeDisabled();
  });
});
