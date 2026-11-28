import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tabs } from "./Tabs";

describe("Tabs", () => {
  it("shows the three tabs and marks the current one", () => {
    render(<Tabs current="favorites" unread={0} onChange={() => {}} />);

    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "商品を探す",
      "お気に入り",
      "自動",
    ]);
    expect(screen.getByRole("tab", { name: "お気に入り" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "商品を探す" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("shows the unread count on the auto-purchase tab", () => {
    render(<Tabs current="search" unread={2} onChange={() => {}} />);

    expect(screen.getByRole("tab", { name: /自動/ })).toHaveTextContent("2");
  });

  it("reports the chosen tab", async () => {
    const onChange = vi.fn();
    render(<Tabs current="search" unread={0} onChange={onChange} />);

    await userEvent.click(screen.getByRole("tab", { name: "自動" }));

    expect(onChange).toHaveBeenCalledWith("auto");
  });
});
