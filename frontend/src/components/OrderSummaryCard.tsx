import { formatYen } from "../code";
import type { Product } from "../types";
import type { Mode } from "./OptionsCard";

type Props = {
  product: Product | null;
  paymentLabel: string;
  mode: Mode;
  account: string | null;
  running: boolean;
  locked: boolean;
  onRun: () => void;
  handoffReady: boolean;
  canOpenHandoff: boolean;
  onOpenHandoff: () => void;
};

export function OrderSummaryCard({
  product,
  paymentLabel,
  mode,
  account,
  running,
  locked,
  onRun,
  handoffReady,
  canOpenHandoff,
  onOpenHandoff,
}: Props) {
  const openMode = mode === "handoff" && handoffReady;
  const label = openMode
    ? "確認画面を開く"
    : mode === "order"
      ? "注文確定まで実行する"
      : mode === "handoff"
        ? "確認画面まで進めてブラウザに引き継ぐ"
        : "確認画面まで進める";
  return (
    <section className={`card side${mode === "order" ? " order" : ""}`} aria-label="ご注文内容">
      <div className="ch">
        <span className="step">4</span>
        <h2>ご注文内容</h2>
        {running && <span className="chip">実行中…</span>}
      </div>
      {product === null ? (
        <p className="muted">商品を選ぶと、ここに注文内容が表示されます。</p>
      ) : (
        <div className="sum">
          {running && (
            <p className="hint">
              <span className="spinner" />
              <b>サイトに接続しています…</b>
              混雑時は自動で再試行します（最大 60 秒）。
            </p>
          )}
          <div className="nm">{product.name}</div>
          <div className="pid">ID {product.product_id} ・ 数量 1</div>
          <div className="kv">
            <span>支払方法</span>
            <span>{paymentLabel}</span>
          </div>
          <div className="kv">
            <span>実行モード</span>
            <span>{mode === "order" ? "注文確定まで" : "確認画面まで"}</span>
          </div>
          <div className="kv">
            <span>アカウント</span>
            <span>{account}</span>
          </div>
          <div className="total">
            <span className="muted">商品価格</span>
            <span className="price">
              {formatYen(product.price_yen)}
              <small>円</small>
            </span>
          </div>
        </div>
      )}
      <button
        type="button"
        className={`block${mode === "order" ? " order" : ""}`}
        disabled={openMode ? !canOpenHandoff : locked || running || product === null}
        onClick={openMode ? onOpenHandoff : onRun}
      >
        {label}
      </button>
      <p className="muted center">送料・合計は確認画面で表示されます</p>
    </section>
  );
}
