import type { ApiErrorKind } from "../api";
import { formatYen } from "../code";
import { runError } from "../messages";
import type { OrderResult, StorePickupResult } from "../types";

export type Outcome =
  | { status: "done"; result: StorePickupResult }
  | { status: "error"; kind: ApiErrorKind };

function OrderBanner({ order }: { order: OrderResult }) {
  if (order.status === "submitted") {
    return (
      <div className="banner ok">
        <b>注文が確定しました。</b> 受注番号: {order.order_id}
      </div>
    );
  }
  if (order.status === "rejected") {
    return (
      <div className="banner warn">
        <b>注文は受理されませんでした（注文は作られていません）。</b>{" "}
        {order.reason === "recaptcha"
          ? "サイトの reCAPTCHA により拒否されました。購入はご自身でブラウザから行ってください。"
          : "購入はご自身でブラウザから行ってください。"}
      </div>
    );
  }
  return (
    <div className="banner warn">
      <b>注文の成否が不明です。</b>{" "}
      購入履歴を確認してください。再実行はしないでください（二重注文のおそれ）。
    </div>
  );
}

export function ResultCard({ outcome }: { outcome: Outcome }) {
  if (outcome.status === "error") {
    const { title, detail } = runError(outcome.kind);
    return (
      <section className="card side" aria-label="結果">
        <div className="ch">
          <span className="step">5</span>
          <h2>結果</h2>
          <span className="chip err">エラー</span>
        </div>
        <div className="banner err flush">
          <b>{title}</b> {detail}
        </div>
      </section>
    );
  }
  const { preview, attempts, order } = outcome.result;
  return (
    <section className="card side" aria-label="結果">
      <div className="ch">
        <span className="step done">✓</span>
        <h2>結果</h2>
        <span className="chip ok">確認画面に到達</span>
      </div>
      {order ? (
        <OrderBanner order={order} />
      ) : (
        <div className="banner ok flush">
          <b>確認画面まで進めました。</b>{" "}
          注文は確定していません（購入はご自身でブラウザから行ってください）。
        </div>
      )}
      <dl>
        <dt>商品名</dt>
        <dd>{preview.item_name}</dd>
        <dt>支払方法</dt>
        <dd>{preview.payment_method}</dd>
        <dt>送料</dt>
        <dd>{formatYen(preview.shipping_fee_yen)}円</dd>
        <dt>合計</dt>
        <dd className="price">{formatYen(preview.total_yen)}円</dd>
        <dt>試行回数</dt>
        <dd>{attempts} 回</dd>
      </dl>
    </section>
  );
}
