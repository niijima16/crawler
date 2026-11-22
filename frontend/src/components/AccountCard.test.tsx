import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ACCOUNT, ACCOUNT_B } from "../test-data";
import { json, mockApi } from "../test-utils";
import { AccountCard } from "./AccountCard";

const user = userEvent.setup();

function setup(props: Partial<Parameters<typeof AccountCard>[0]> = {}) {
  const handlers = { onSelect: vi.fn(), onAdded: vi.fn(), onDeleted: vi.fn() };
  render(
    <AccountCard
      accounts={[ACCOUNT, ACCOUNT_B]}
      selectedId="a1"
      notice={null}
      {...handlers}
      {...props}
    />,
  );
  return { ...handlers, card: screen.getByRole("region", { name: "アカウント" }) };
}

afterEach(() => vi.unstubAllGlobals());

describe("AccountCard", () => {
  it("shows a loading state", () => {
    const { card } = setup({ accounts: null, selectedId: null });

    expect(card).toHaveTextContent("読み込み中");
  });

  it("asks for the first account when none is registered", () => {
    const { card } = setup({ accounts: [], selectedId: null });

    expect(card).toHaveTextContent("未ログイン");
    expect(within(card).getByLabelText("メールアドレス")).toBeInTheDocument();
    expect(within(card).getByLabelText("パスワード")).toBeInTheDocument();
  });

  it("lists the accounts with masked emails and marks the one in use", async () => {
    const { card, onSelect } = setup();

    expect(card).toHaveTextContent("ログイン済み");
    expect(card).toHaveTextContent("t***@example.com");
    expect(card).toHaveTextContent("s***@example.com");
    expect(card).not.toHaveTextContent("tester@example.com");
    expect(card).toHaveTextContent("使用中");

    await user.click(within(card).getByRole("button", { name: "切り替える" }));

    expect(onSelect).toHaveBeenCalledWith("a2");
  });

  it("adds an account after verifying the login and clears the password", async () => {
    const { calls } = mockApi({ "POST /api/accounts": () => json(200, ACCOUNT_B) });
    const { card, onAdded } = setup();

    await user.click(within(card).getByRole("button", { name: "アカウントを追加" }));
    await user.type(within(card).getByLabelText("ラベル"), "テスト用 B");
    await user.type(within(card).getByLabelText("メールアドレス"), "sato@example.com");
    await user.type(within(card).getByLabelText("パスワード"), "secret-pw");
    await user.click(within(card).getByRole("button", { name: "ログインを確認して追加" }));

    await waitFor(() => expect(onAdded).toHaveBeenCalledWith(ACCOUNT_B));
    expect(calls[0].body).toEqual({
      label: "テスト用 B",
      email: "sato@example.com",
      password: "secret-pw",
    });
    expect(screen.queryByLabelText("パスワード")).not.toBeInTheDocument();
  });

  it.each([
    [401, { detail: "login failed" }, /ログインに失敗しました/],
    [409, { detail: "duplicate_account" }, /すでに登録されています/],
    [502, { detail: "upstream request failed" }, /サイトに接続できません/],
  ])("explains a %s error when adding", async (status, body, message) => {
    mockApi({ "POST /api/accounts": () => json(status, body) });
    const { card, onAdded } = setup({ accounts: [], selectedId: null });

    await user.type(within(card).getByLabelText("メールアドレス"), "a@example.test");
    await user.type(within(card).getByLabelText("パスワード"), "bad");
    await user.click(within(card).getByRole("button", { name: "ログインを確認して追加" }));

    expect(await within(card).findByText(message)).toBeInTheDocument();
    expect(onAdded).not.toHaveBeenCalled();
  });

  it("deletes an account only after a second click", async () => {
    const { calls } = mockApi({
      "DELETE /api/accounts/a2": () => new Response(null, { status: 204 }),
    });
    const { card, onDeleted } = setup();

    await user.click(within(card).getAllByRole("button", { name: "削除" })[0]);
    expect(calls).toHaveLength(0);
    expect(card).toHaveTextContent("お気に入りも削除されます");

    await user.click(within(card).getByRole("button", { name: "削除する" }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("a2"));
  });

  it("shows a notice", () => {
    const { card } = setup({ notice: "ログイン情報が無効になりました。" });

    expect(card).toHaveTextContent("ログイン情報が無効になりました");
  });
});
