import { type FormEvent, useState } from "react";
import { ApiError, api } from "../api";
import { favoriteError } from "../messages";
import type { Genre, KeywordFavorite, PaymentMethod } from "../types";

type Props = {
  accountId: string;
  genres: Genre[];
  methods: PaymentMethod[];
  onAdded: (favorite: KeywordFavorite) => void;
};

const DEFAULT_GENRE_ID = 22;

export function KeywordFavoriteForm({ accountId, genres, methods, onAdded }: Props) {
  const [keyword, setKeyword] = useState("");
  const [categoryId, setCategoryId] = useState(DEFAULT_GENRE_ID);
  const [payment, setPayment] = useState("8");
  const [cap, setCap] = useState("");
  const [error, setError] = useState<string | null>(null);

  const payable = methods.filter((m) => m.preview_supported);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (keyword.trim() === "") return;
    setError(null);
    try {
      const favorite = await api.addKeywordFavorite({
        account_id: accountId,
        keyword: keyword.trim(),
        category_id: categoryId,
        payment_method: payment,
        price_cap_yen: cap.trim() === "" ? null : Number(cap),
      });
      setKeyword("");
      setCap("");
      onAdded(favorite);
    } catch (caught) {
      const kind = caught instanceof ApiError ? caught.kind : "network";
      setError(
        kind === "limit"
          ? "キーワードお気に入りは 10 件までです。解除してから登録してください。"
          : favoriteError(kind),
      );
    }
  }

  return (
    <section className="card" aria-label="キーワードお気に入りを登録">
      <div className="ch">
        <span className="step">＋</span>
        <h2>キーワードお気に入りを登録</h2>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        キーワード（部分一致）とジャンルで見張り、新しく出てきた可能な商品を検知して通知します。確認画面まで進めてブラウザに引き継ぎ、最後の「する」はブラウザで自分が押します。
      </p>
      <form className="row" onSubmit={submit}>
        <label className="field">
          キーワード
          <input type="text" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        </label>
        <label className="field">
          ジャンル
          <select
            aria-label="ジャンル"
            value={categoryId}
            onChange={(e) => setCategoryId(Number(e.target.value))}
          >
            {genres.map((g) => (
              <option key={g.category_id} value={g.category_id}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          支払方法
          <select
            aria-label="支払方法"
            value={payment}
            onChange={(e) => setPayment(e.target.value)}
          >
            {payable.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          価格上限（任意）
          <input
            type="number"
            min="0"
            value={cap}
            placeholder="なし"
            onChange={(e) => setCap(e.target.value)}
          />
        </label>
        <button type="submit" className="dark">
          登録する
        </button>
      </form>
      <p className="hint">
        クレジットカードは選べません（確認画面まで進めないため）。登録後の最初の監視で、今ある可能な一致商品も通知します（その後は新しく出たものが対象）。
      </p>
      {error && <div className="banner err">{error}</div>}
    </section>
  );
}
