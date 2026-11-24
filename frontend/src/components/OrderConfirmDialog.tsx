import { formatYen } from "../code";
import type { Product } from "../types";

type Props = {
  product: Product;
  paymentLabel: string;
  account: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function OrderConfirmDialog({ product, paymentLabel, account, onConfirm, onCancel }: Props) {
  return (
    <div className="backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-label="注文確定の確認">
        <h2>注文確定まで実行しますか？</h2>
        <dl>
          <dt>商品</dt>
          <dd>{product.name}</dd>
          <dt>価格</dt>
          <dd>{formatYen(product.price_yen)}円</dd>
          <dt>支払方法</dt>
          <dd>{paymentLabel}</dd>
          <dt>アカウント</dt>
          <dd>{account}</dd>
        </dl>
        <p className="muted">「する」を 1 回だけ送信します。取り消しにくい操作です。</p>
        <div className="row end">
          <button type="button" className="secondary" onClick={onCancel}>
            キャンセル
          </button>
          <button type="button" className="danger" onClick={onConfirm}>
            注文確定まで実行する
          </button>
        </div>
      </div>
    </div>
  );
}
