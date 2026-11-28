/** 入力（`815572`、`product/815572`、商品ページの URL）から商品 ID を取り出す。 */
export function parseProductCode(input: string): number | null {
  const text = input.trim();
  const match = /^\d{1,12}$/.test(text)
    ? [text, text]
    : /(?:^|\/)product\/(\d{1,12})(?:[/?#]|$)/.exec(text);
  return match ? Number(match[1]) : null;
}

/** 金額を桁区切りにする（「円」は呼び出し側で付ける）。 */
export function formatYen(amount: number): string {
  return amount.toLocaleString("ja-JP");
}
