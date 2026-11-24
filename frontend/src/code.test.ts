import { parseProductCode } from "./code";

describe("parseProductCode", () => {
  it.each([
    ["815572", 815572],
    [" 815572 ", 815572],
    ["product/815572", 815572],
    ["/product/815572", 815572],
    ["https://www.example.com/product/815572", 815572],
    ["https://www.example.com/product/815572?x=1", 815572],
    ["https://www.example.com/product/815572/", 815572],
  ])("extracts the id from %s", (input, expected) => {
    expect(parseProductCode(input)).toBe(expected);
  });

  it.each(["", "   ", "abc", "12ab", "product/", "https://example.test/"])(
    "returns null for %j",
    (input) => {
      expect(parseProductCode(input)).toBeNull();
    },
  );
});
