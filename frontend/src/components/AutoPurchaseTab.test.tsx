import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NOTE_NEW_ARRIVAL, NOTE_PURCHASED, NOTE_REJECTED, STATUS } from "../test-data";
import { json, mockApi } from "../test-utils";
import { AutoPurchaseTab } from "./AutoPurchaseTab";

const user = userEvent.setup();
const NOW = new Date("2026-11-22T11:00:00Z");

function setup(props: Partial<Parameters<typeof AutoPurchaseTab>[0]> = {}) {
  const onChanged = vi.fn();
  const onOpenConfirmation = vi.fn();
  const onAutoOpenChange = vi.fn();
  render(
    <AutoPurchaseTab
      status={STATUS}
      notifications={{ unread: 1, items: [NOTE_REJECTED, NOTE_PURCHASED] }}
      now={NOW}
      onChanged={onChanged}
      onOpenConfirmation={onOpenConfirmation}
      autoOpen={false}
      onAutoOpenChange={onAutoOpenChange}
      {...props}
    />,
  );
  return {
    onChanged,
    onOpenConfirmation,
    onAutoOpenChange,
    tab: screen.getByRole("region", { name: "自動" }),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("AutoPurchaseTab", () => {
  it("shows the latest auto handoff result in one line", () => {
    setup({ autoLine: { text: "自動: 新着: X の確認画面を開きました", tone: "ok" } });

    expect(screen.getByText("自動: 新着: X の確認画面を開きました")).toBeInTheDocument();
  });

  it("cannot open a confirmation by hand while an auto handoff runs", () => {
    setup({ manualBlocked: true, notifications: { unread: 1, items: [NOTE_NEW_ARRIVAL] } });

    expect(screen.getByRole("button", { name: "確認画面を開く" })).toBeDisabled();
  });

  it("has a switch to open the confirmation automatically on new arrivals", async () => {
    const { onAutoOpenChange } = setup();

    const toggle = screen.getByRole("switch", { name: "新着通知で自動で確認画面を開く" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);

    expect(onAutoOpenChange).toHaveBeenCalledWith(true);
  });

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

    await user.click(within(tab).getByRole("switch", { name: "自動" }));

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

  it("deletes one notification", async () => {
    const { calls } = mockApi({
      [`DELETE /api/notifications/${NOTE_REJECTED.id}`]: () => new Response(null, { status: 204 }),
    });
    const { tab, onChanged } = setup({ notifications: { unread: 1, items: [NOTE_REJECTED] } });

    await user.click(within(tab).getByRole("button", { name: "削除" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls.map((c) => c.key)).toEqual([`DELETE /api/notifications/${NOTE_REJECTED.id}`]);
  });

  it("deletes all notifications after confirming", async () => {
    const { calls } = mockApi({
      "DELETE /api/notifications": () => new Response(null, { status: 204 }),
    });
    const { tab, onChanged } = setup();

    await user.click(within(tab).getByRole("button", { name: "すべて削除" }));
    expect(tab).toHaveTextContent("通知をすべて削除します");
    await user.click(within(tab).getByRole("button", { name: "削除する" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls.map((c) => c.key)).toEqual(["DELETE /api/notifications"]);
  });

  it("does not delete anything when the confirmation is cancelled", async () => {
    const { calls } = mockApi({});
    const { tab, onChanged } = setup();

    await user.click(within(tab).getByRole("button", { name: "すべて削除" }));
    await user.click(within(tab).getByRole("button", { name: "やめる" }));

    expect(calls).toEqual([]);
    expect(onChanged).not.toHaveBeenCalled();
    expect(within(tab).getByRole("button", { name: "すべて削除" })).toBeEnabled();
  });

  it("cannot delete all when there are no notifications", () => {
    const { tab } = setup({ notifications: { unread: 0, items: [] } });

    expect(within(tab).getByRole("button", { name: "すべて削除" })).toBeDisabled();
  });

  it("shows an empty state", () => {
    const { tab } = setup({ notifications: { unread: 0, items: [] } });

    expect(tab).toHaveTextContent("通知はまだありません");
  });

  it("shows a loading state before the status arrives", () => {
    setup({ status: null });

    expect(screen.getByRole("region", { name: "自動" })).toHaveTextContent("読み込み中");
  });
});

describe("AutoPurchaseTab new arrivals", () => {
  it("offers 確認画面を開く on a new-arrival notification and reports it", async () => {
    const { onOpenConfirmation } = setup({
      notifications: { unread: 1, items: [NOTE_NEW_ARRIVAL] },
    });

    await user.click(screen.getByRole("button", { name: "確認画面を開く" }));

    expect(onOpenConfirmation).toHaveBeenCalledWith(NOTE_NEW_ARRIVAL);
  });

  it("does not show 確認画面を開く on non-arrival notifications", () => {
    setup({ notifications: { unread: 1, items: [NOTE_REJECTED] } });

    expect(screen.queryByRole("button", { name: "確認画面を開く" })).not.toBeInTheDocument();
  });
});
