import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NOTE_PURCHASED, NOTE_REJECTED, STATUS } from "../test-data";
import { json, mockApi } from "../test-utils";
import { AutoPurchaseTab } from "./AutoPurchaseTab";

const user = userEvent.setup();
const NOW = new Date("2026-11-22T11:00:00Z");

function setup(props: Partial<Parameters<typeof AutoPurchaseTab>[0]> = {}) {
  const onChanged = vi.fn();
  render(
    <AutoPurchaseTab
      status={STATUS}
      notifications={{ unread: 1, items: [NOTE_REJECTED, NOTE_PURCHASED] }}
      now={NOW}
      onChanged={onChanged}
      {...props}
    />,
  );
  return { onChanged, tab: screen.getByRole("region", { name: "自動購入" }) };
}

afterEach(() => vi.unstubAllGlobals());

describe("AutoPurchaseTab", () => {
  it("shows the time until the nightly check, the worker and the order permission", () => {
    const { tab } = setup();

    expect(tab).toHaveTextContent("1 時間 23 分");
    expect(tab).toHaveTextContent("稼働中");
    expect(tab).toHaveTextContent("有効");
    expect(tab).not.toHaveTextContent("注文確定が無効になっています");
  });

  it("warns when order submission is not allowed on the server", () => {
    const { tab } = setup({ status: { ...STATUS, order_submit_allowed: false } });

    expect(tab).toHaveTextContent("注文確定が無効になっています");
    expect(tab).toHaveTextContent("ALLOW_ORDER_SUBMIT");
  });

  it("warns when the worker has stopped or has never run", () => {
    expect(
      setup({ status: { ...STATUS, last_tick_at: "2026-11-22T10:00:00Z" } }).tab,
    ).toHaveTextContent("停止している可能性");
  });

  it("switches automatic purchasing on and off", async () => {
    const { calls } = mockApi({ "PUT /api/auto-purchase/enabled": () => json(200, STATUS) });
    const { tab, onChanged } = setup();

    await user.click(within(tab).getByRole("switch", { name: "自動購入" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls[0].body).toEqual({ enabled: false });
  });

  it("lists the results with the unread ones marked, and never the monitoring details", () => {
    const { tab } = setup();

    expect(tab).toHaveTextContent("未読 1");
    expect(tab).toHaveTextContent("reCAPTCHA により注文は受理されませんでした");
    expect(tab).toHaveTextContent("受注番号 96301");
    expect(tab).toHaveTextContent("1 分ごとの監視の中身は表示しません");
  });

  it("marks everything as read", async () => {
    const { calls } = mockApi({ "POST /api/notifications/read": () => json(200, { unread: 0 }) });
    const { tab, onChanged } = setup();

    await user.click(within(tab).getByRole("button", { name: "すべて既読にする" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls[0].key).toBe("POST /api/notifications/read");
  });

  it("shows an empty state", () => {
    const { tab } = setup({ notifications: { unread: 0, items: [] } });

    expect(tab).toHaveTextContent("通知はまだありません");
  });

  it("shows a loading state before the status arrives", () => {
    setup({ status: null });

    expect(screen.getByRole("region", { name: "自動購入" })).toHaveTextContent("読み込み中");
  });
});
