import { useState } from "react";
import type { Favorite, Product } from "../types";

type Props = {
  product: Product;
  selected: boolean;
  onSelect: (product: Product) => void;
  favorite: Favorite | null;
  canFavorite: boolean;
  onFavorite: (product: Product) => void;
};

export function ProductCard({
  product,
  selected,
  onSelect,
  favorite,
  canFavorite,
  onFavorite,
}: Props) {
  const [consenting, setConsenting] = useState(false);
  const isFavorite = favorite !== null;
  return (
    <div className={`pcard${selected ? " sel" : ""}`}>
      <div className="pimg">
        <span className={`badge${product.in_stock ? "" : " out"}`}>
          {product.in_stock ? "在庫あり" : "在庫なし"}
        </span>
        <button
          type="button"
          className={`star${isFavorite ? " on" : ""}`}
          aria-label={isFavorite ? "お気に入り済み" : "お気に入りに登録"}
          title={
            canFavorite
              ? undefined
              : "この支払方法では自動できません（店頭支払・代金引換・銀行振込・郵便振替を選んでください）"
          }
          disabled={isFavorite || !canFavorite}
          onClick={() => setConsenting(true)}
        >
          {isFavorite ? "★" : "☆"}
        </button>
        画像なし
      </div>
      <div className="pbody">
        <div className="nm">{product.name}</div>
        <div className="pid">ID {product.product_id}</div>
        <div className="price">
          {product.price_yen.toLocaleString("ja-JP")}
          <small>円</small>
        </div>
        {consenting && !isFavorite && (
          <div className="consent">
            <p>お気に入りに登録すると、可能になった時点で自動で注文確定まで進みます。</p>
            <div className="row">
              <button
                type="button"
                className="dark"
                onClick={() => {
                  setConsenting(false);
                  onFavorite(product);
                }}
              >
                登録する
              </button>
              <button type="button" className="secondary" onClick={() => setConsenting(false)}>
                キャンセル
              </button>
            </div>
          </div>
        )}
        {selected ? (
          <button type="button" className="secondary" disabled>
            選択中 ✓
          </button>
        ) : (
          <button type="button" className="dark" onClick={() => onSelect(product)}>
            この商品を選ぶ
          </button>
        )}
      </div>
    </div>
  );
}
