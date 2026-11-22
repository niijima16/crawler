import { type FormEvent, useState } from "react";
import { ApiError, api } from "../api";
import { parseProductCode } from "../code";
import { searchError } from "../messages";
import type { Favorite, Product } from "../types";
import type { SearchMode } from "./OptionsCard";
import { ProductCard } from "./ProductCard";

type Props = {
  searchMode: SearchMode;
  disabled: boolean;
  selectedId: number | null;
  onSelect: (product: Product) => void;
  favorites: Favorite[];
  canFavorite: boolean;
  favoriteMessage: string | null;
  onFavorite: (product: Product) => void;
};

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; products: Product[] }
  | { status: "error"; message: string };

export function SearchCard({
  searchMode,
  disabled,
  selectedId,
  onSelect,
  favorites,
  canFavorite,
  favoriteMessage,
  onFavorite,
}: Props) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<State>({ status: "idle" });

  async function search(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (searchMode === "code") {
      const code = parseProductCode(text);
      if (code === null) {
        setState({ status: "error", message: "商品コードの数字を入力してください。" });
        return;
      }
      await run(() => api.searchByCode(code));
    } else if (text === "") {
      setState({ status: "error", message: "キーワードを入力してください。" });
    } else {
      await run(() => api.searchByKeyword(text));
    }
  }

  async function run(load: () => Promise<Product[]>) {
    setState({ status: "loading" });
    try {
      setState({ status: "done", products: await load() });
    } catch (error) {
      const kind = error instanceof ApiError ? error.kind : "network";
      setState({ status: "error", message: searchError(kind) });
    }
  }

  return (
    <section className="card" aria-label="商品を探す">
      <div className="ch">
        <span className="step">3</span>
        <h2>商品を探す</h2>
        {state.status === "done" && state.products.length > 0 && (
          <span className="chip">{state.products.length} 件（先頭 1 ページ）</span>
        )}
      </div>
      <form className="row" onSubmit={search}>
        <input
          className="grow"
          type="text"
          aria-label="検索語"
          value={query}
          disabled={disabled}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit" disabled={disabled}>
          検索
        </button>
      </form>
      {searchMode === "code" && (
        <p className="hint">
          コード検索は商品 ID（<code>815572</code>、<code>product/815572</code>、商品ページの
          URL）に対応します。
        </p>
      )}
      {state.status === "loading" && <p className="hint">検索しています…</p>}
      {state.status === "error" && <div className="banner err">{state.message}</div>}
      {favoriteMessage && <div className="banner err">{favoriteMessage}</div>}
      {state.status === "done" && state.products.length === 0 && (
        <p className="hint">見つかりませんでした。</p>
      )}
      {state.status === "done" && state.products.length > 0 && (
        <div className="products">
          {state.products.map((product) => (
            <ProductCard
              key={product.product_id}
              product={product}
              selected={product.product_id === selectedId}
              onSelect={onSelect}
              favorite={favorites.find((f) => f.product_id === product.product_id) ?? null}
              canFavorite={canFavorite}
              onFavorite={onFavorite}
            />
          ))}
        </div>
      )}
    </section>
  );
}
