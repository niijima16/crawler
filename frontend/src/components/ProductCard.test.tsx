import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { favorite, MAME } from "../test-data";
import { ProductCard } from "./ProductCard";

function setup(props: Partial<Parameters<typeof ProductCard>[0]> = {}) {
  const onFavorite = vi.fn();
  render(
    <ProductCard
      product={MAME}
      selected={false}
      onSelect={() => {}}
      favorite={null}
      canFavorite={true}
      onFavorite={onFavorite}
      {...props}
    />,
  );
  return { onFavorite };
}

describe("ProductCard favorites", () => {
  it("asks for consent before registering a favorite", async () => {
    const { onFavorite } = setup();

    await userEvent.click(screen.getByRole("button", { name: "お気に入りに登録" }));

    expect(screen.getByText(/自動で注文確定まで進みます/)).toBeInTheDocument();
    expect(onFavorite).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "登録する" }));

    expect(onFavorite).toHaveBeenCalledWith(MAME);
  });

  it("can be cancelled", async () => {
    const { onFavorite } = setup();
    await userEvent.click(screen.getByRole("button", { name: "お気に入りに登録" }));

    await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(screen.queryByText(/自動で注文確定まで進みます/)).not.toBeInTheDocument();
    expect(onFavorite).not.toHaveBeenCalled();
  });

  it("shows a filled star for a favorite and cannot register it again", () => {
    setup({ favorite: favorite() });

    expect(screen.getByRole("button", { name: "お気に入り済み" })).toBeDisabled();
  });

  it("explains why a favorite cannot be registered", () => {
    setup({ canFavorite: false });

    const star = screen.getByRole("button", { name: "お気に入りに登録" });
    expect(star).toBeDisabled();
    expect(star).toHaveAttribute("title", expect.stringContaining("自動購入"));
  });
});
