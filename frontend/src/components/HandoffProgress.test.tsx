import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HandoffProgress } from "./HandoffProgress";

type Listener = (event: { data: string }) => void;

class FakeEventSource {
  static last: FakeEventSource | null = null;
  listeners: Record<string, Listener> = {};
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, cb: Listener) {
    this.listeners[type] = cb;
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    this.listeners[type]?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  FakeEventSource.last = null;
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

function setup(extensionInstalled = true) {
  const onReady = vi.fn();
  const onClose = vi.fn();
  render(
    <HandoffProgress
      accountId="a1"
      productId={815572}
      paymentMethod="8"
      extensionInstalled={extensionInstalled}
      onReady={onReady}
      onClose={onClose}
    />,
  );
  const source = FakeEventSource.last as FakeEventSource;
  const region = screen.getByRole("region", { name: "確認画面への引き継ぎ" });
  const emit = (type: string, data: unknown) => act(() => source.emit(type, data));
  return { onReady, onClose, source, region, emit };
}

it("opens the stream with the account and product in the URL", () => {
  const { source } = setup();
  expect(source.url).toContain("account_id=a1");
  expect(source.url).toContain("product_id=815572");
  expect(source.url).toContain("payment_method=8");
});

it("marks steps done as they progress and hands off on done", () => {
  const { emit, region, onReady } = setup();

  emit("step", { step: "login", status: "started", attempt: 1 });
  emit("step", { step: "login", status: "done", attempt: 1 });
  emit("step", { step: "cart", status: "started", attempt: 1 });

  const login = within(region).getByText("ログイン").closest("li");
  const cart = within(region).getByText("カートに追加").closest("li");
  expect(login).toHaveClass("done");
  expect(cart).toHaveClass("active");

  const handoff = { cookie_name: "PHPSESSID", cookie_value: "sess-xyz", confirm_url: "u" };
  emit("done", handoff);
  expect(onReady).toHaveBeenCalledWith(handoff);
  expect(region).toHaveTextContent("確認画面をブラウザで開きました");
});

it("shows the retry count while a step is retried", () => {
  const { emit, region } = setup();
  emit("step", { step: "confirm", status: "started", attempt: 2 });
  expect(region).toHaveTextContent("再試行 2");
});

it("shows an error when the stream reports one", () => {
  const { emit, region } = setup();
  emit("error", { reason: "not_purchasable" });
  expect(region).toHaveTextContent("引き継ぎに失敗しました");
});

it("tells the user to install the extension when it is missing", () => {
  const { emit, region } = setup(false);
  emit("done", { cookie_name: "PHPSESSID", cookie_value: "x", confirm_url: "u" });
  expect(region).toHaveTextContent("拡張機能を入れると");
});

function setupAuto() {
  const onError = vi.fn();
  render(
    <HandoffProgress
      accountId="a1"
      productId={815572}
      paymentMethod="8"
      extensionInstalled
      onReady={vi.fn()}
      onClose={vi.fn()}
      auto
      onError={onError}
    />,
  );
  const source = FakeEventSource.last as FakeEventSource;
  return { source, onError };
}

it("asks the server to persist (auto=true) only for an auto handoff", () => {
  const { source } = setupAuto();
  expect(source.url).toContain("auto=true");
});

it("does not add auto for a manual handoff", () => {
  const { source } = setup();
  expect(source.url).not.toContain("auto=");
});

it("tells the parent why the handoff failed", () => {
  const { source, onError } = setupAuto();
  act(() => source.emit("error", { reason: "timeout" }));
  expect(onError).toHaveBeenCalledWith("timeout");
});
