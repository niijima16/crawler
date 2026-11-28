import { render, screen } from "@testing-library/react";
import { MAME } from "../test-data";
import { OrderSummaryCard } from "./OrderSummaryCard";

it("cannot run while an auto handoff runs, and says why", () => {
  render(
    <OrderSummaryCard
      product={MAME}
      paymentLabel="店頭払い"
      mode="handoff"
      account={null}
      running={false}
      locked={false}
      blocked
      onRun={() => undefined}
    />,
  );

  expect(
    screen.getByRole("button", { name: "確認画面まで進めてブラウザに引き継ぐ" }),
  ).toBeDisabled();
  expect(
    screen.getByText("自動の引き継ぎ中は使えません（スイッチを OFF にすると使えます）"),
  ).toBeInTheDocument();
});
