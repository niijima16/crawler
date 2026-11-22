import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MAME } from "../test-data";
import { OrderConfirmDialog } from "./OrderConfirmDialog";

function setup() {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <OrderConfirmDialog
      product={MAME}
      paymentLabel="店頭支払"
      account="n***@gmail.com"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
  return { onConfirm, onCancel, dialog: screen.getByRole("dialog") };
}

describe("OrderConfirmDialog", () => {
  it("shows what is about to be ordered", () => {
    const { dialog } = setup();

    expect(dialog).toHaveTextContent("SD/豆本 S-26-11-01-584-TO-ZS");
    expect(dialog).toHaveTextContent("990円");
    expect(dialog).toHaveTextContent("店頭支払");
    expect(dialog).toHaveTextContent("n***@gmail.com");
    expect(dialog).toHaveTextContent("1 回だけ送信");
  });

  it("confirms or cancels explicitly", async () => {
    const { onConfirm, onCancel } = setup();

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "注文確定まで実行する" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
