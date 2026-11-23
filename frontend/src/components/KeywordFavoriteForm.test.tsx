import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GENRES, METHODS } from "../test-data";
import { json, mockApi } from "../test-utils";
import { KeywordFavoriteForm } from "./KeywordFavoriteForm";

const user = userEvent.setup();

function setup() {
  const onAdded = vi.fn();
  render(
    <KeywordFavoriteForm accountId="a1" genres={GENRES} methods={METHODS} onAdded={onAdded} />,
  );
  return { onAdded, form: screen.getByRole("region", { name: "キーワードお気に入りを登録" }) };
}

afterEach(() => vi.unstubAllGlobals());

describe("KeywordFavoriteForm", () => {
  it("has a keyword input, a genre dropdown (default SuperDollfie), payment and price cap", () => {
    const { form } = setup();

    expect(within(form).getByLabelText("キーワード")).toBeInTheDocument();
    const genre = within(form).getByRole("combobox", { name: "ジャンル" });
    expect(genre).toHaveValue("22");
    expect(within(genre).getAllByRole("option")).toHaveLength(GENRES.length);
    expect(within(form).getByLabelText("価格上限（任意）")).toBeInTheDocument();
  });

  it("does not offer the credit card as a payment method", () => {
    const { form } = setup();
    const select = within(form).getByRole("combobox", { name: "支払方法" });

    expect(
      within(select).queryByRole("option", { name: /クレジットカード/ }),
    ).not.toBeInTheDocument();
    expect(within(select).getAllByRole("option").length).toBe(7);
  });

  it("registers with the chosen keyword, genre, payment and cap", async () => {
    const { calls } = mockApi({
      "POST /api/keyword-favorites": () => json(200, { id: "k1" }),
    });
    const { form, onAdded } = setup();

    await user.type(within(form).getByLabelText("キーワード"), "豆本");
    await user.selectOptions(within(form).getByRole("combobox", { name: "ジャンル" }), "136");
    await user.selectOptions(within(form).getByRole("combobox", { name: "支払方法" }), "3");
    await user.type(within(form).getByLabelText("価格上限（任意）"), "3000");
    await user.click(within(form).getByRole("button", { name: "登録する" }));

    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(calls[0].body).toEqual({
      account_id: "a1",
      keyword: "豆本",
      category_id: 136,
      payment_method: "3",
      price_cap_yen: 3000,
    });
  });

  it("sends a null cap when left blank and requires a keyword", async () => {
    const { calls } = mockApi({ "POST /api/keyword-favorites": () => json(200, { id: "k1" }) });
    const { form } = setup();

    await user.click(within(form).getByRole("button", { name: "登録する" }));
    expect(calls).toHaveLength(0); // キーワード必須

    await user.type(within(form).getByLabelText("キーワード"), "豆本");
    await user.click(within(form).getByRole("button", { name: "登録する" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({ keyword: "豆本", category_id: 22, price_cap_yen: null });
  });

  it("shows an error when the limit is reached", async () => {
    mockApi({ "POST /api/keyword-favorites": () => json(409, { detail: "favorite_limit" }) });
    const { form } = setup();

    await user.type(within(form).getByLabelText("キーワード"), "豆本");
    await user.click(within(form).getByRole("button", { name: "登録する" }));

    expect(await within(form).findByText(/10 件/)).toBeInTheDocument();
  });
});
