import { type FormEvent, useState } from "react";
import { ApiError, api, type FavoritePatch } from "../api";
import { favoriteError } from "../messages";
import type { Favorite, FavoriteState, PaymentMethod } from "../types";

const MAX_FAVORITES = 20;

const STATE_LABEL: Record<FavoriteState, { text: string; className: string }> = {
  watching: { text: "監視中", className: "watch" },
  purchasing: { text: "購入処理中", className: "buying" },
  purchased: { text: "購入済み", className: "done" },
  rejected: { text: "受理されず", className: "rej" },
  unknown: { text: "成否不明", className: "rej" },
  stopped: { text: "停止", className: "stop" },
};

type Props = { favorites: Favorite[]; methods: PaymentMethod[]; onChanged: () => void };

export function FavoritesTab({ favorites, methods, onChanged }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [payment, setPayment] = useState("8");
  const [cap, setCap] = useState("");
  const [error, setError] = useState<string | null>(null);

  const label = (id: string) => methods.find((m) => m.id === id)?.label ?? id;
  const watching = favorites.filter((f) => f.state === "watching").length;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setEditingId(null);
      onChanged();
    } catch (caught) {
      setError(favoriteError(caught instanceof ApiError ? caught.kind : "network"));
    }
  }

  function startEdit(favorite: Favorite) {
    setEditingId(favorite.id);
    setPayment(favorite.payment_method);
    setCap(favorite.price_cap_yen === null ? "" : String(favorite.price_cap_yen));
  }

  function save(event: FormEvent, favorite: Favorite) {
    event.preventDefault();
    const patch: FavoritePatch = {
      payment_method: payment,
      price_cap_yen: cap.trim() === "" ? null : Number(cap),
    };
    run(() => api.updateFavorite(favorite.id, patch));
  }

  return (
    <section className="card" aria-label="お気に入り">
      <div className="ch">
        <span className="step">★</span>
        <h2>お気に入り</h2>
        <span className="chip">
          {favorites.length === 0
            ? `0 / ${MAX_FAVORITES} 件`
            : `監視中 ${watching} / 全 ${favorites.length} 件（上限 ${MAX_FAVORITES}）`}
        </span>
      </div>
      {favorites.length === 0 ? (
        <p className="empty">
          お気に入りはまだありません。「商品を探す」で ☆
          を押すと、購入可能になったとき自動で注文確定まで進みます。
        </p>
      ) : (
        <ul className="favlist">
          {favorites.map((favorite) => {
            const state = STATE_LABEL[favorite.state];
            const busy = favorite.state === "purchasing";
            const finished = ["purchased", "rejected", "unknown", "stopped"].includes(
              favorite.state,
            );
            return (
              <li key={favorite.id} className="fav">
                <div className="pimg">画像なし</div>
                <div>
                  <div className="nm">
                    {favorite.product_name}{" "}
                    <span className={`st ${state.className}`}>{state.text}</span>
                  </div>
                  <div className="pid">ID {favorite.product_id}</div>
                  <div className="meta">
                    <span>支払方法: {label(favorite.payment_method)}</span>
                    <span>
                      価格上限:{" "}
                      {favorite.price_cap_yen === null
                        ? "なし"
                        : `${favorite.price_cap_yen.toLocaleString("ja-JP")}円`}
                    </span>
                  </div>
                  {editingId === favorite.id && (
                    <form className="row gap-top" onSubmit={(event) => save(event, favorite)}>
                      <label className="field">
                        支払方法
                        <select
                          aria-label="支払方法"
                          value={payment}
                          onChange={(event) => setPayment(event.target.value)}
                        >
                          {methods
                            .filter((m) => m.submit_supported)
                            .map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.label}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label className="field">
                        価格上限（円）
                        <input
                          type="number"
                          min="0"
                          value={cap}
                          placeholder="なし"
                          onChange={(event) => setCap(event.target.value)}
                        />
                      </label>
                      <button type="submit" className="dark">
                        保存
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setEditingId(null)}
                      >
                        キャンセル
                      </button>
                    </form>
                  )}
                </div>
                <div className="act">
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => startEdit(favorite)}
                  >
                    編集
                  </button>
                  {finished && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => run(() => api.updateFavorite(favorite.id, { resume: true }))}
                    >
                      再開
                    </button>
                  )}
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => run(() => api.deleteFavorite(favorite.id))}
                  >
                    解除
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {error && <div className="banner err">{error}</div>}
    </section>
  );
}
