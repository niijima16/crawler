import { useState } from "react";
import type { CheckoutPreview, Handoff } from "../types";

type Props = {
  preview: CheckoutPreview;
  handoff: Handoff;
  extensionInstalled: boolean;
};

export function HandoffCard({ preview, handoff, extensionInstalled }: Props) {
  const [revealed, setRevealed] = useState(false);
  return (
    <section className="card" aria-label="ブラウザで購入する">
      <div className="ch">
        <span className="step done">✓</span>
        <h2>ブラウザで購入する</h2>
        <span className={`chip${extensionInstalled ? " ok" : " warn"}`}>
          {extensionInstalled ? "拡張が有効" : "拡張が未検出"}
        </span>
      </div>
      <div className="banner ok flush">
        <b>確認画面まで進めました。</b> 確認画面をあなたのブラウザで開きます。
        <b>最後の「購入する」は、ブラウザで自分で押してください。</b>
      </div>
      <dl>
        <dt>商品</dt>
        <dd>{preview.item_name}</dd>
        <dt>支払方法</dt>
        <dd>{preview.payment_method}</dd>
        <dt>送料</dt>
        <dd>{preview.shipping_fee_yen.toLocaleString("ja-JP")}円</dd>
        <dt>合計</dt>
        <dd className="price">{preview.total_yen.toLocaleString("ja-JP")}円</dd>
      </dl>
      {extensionInstalled ? (
        <p className="hint">
          確認画面をブラウザの別タブに開きました。開かない場合は、上の「確認画面を開く」を押してください。
        </p>
      ) : (
        <>
          <div className="banner warn flush">
            <b>1クリックで開くには、ブラウザ拡張が必要です。</b> <code>browser-extension/</code>{" "}
            を読み込むと、次回から「確認画面を開く」1つで済みます。
          </div>
          <h3>拡張なしで進める（DevTools 手動）</h3>
          <div className="secret">
            <span className="val">
              {handoff.cookie_name} = {revealed ? handoff.cookie_value : "•".repeat(32)}
            </span>
            <button type="button" className="ghost" onClick={() => setRevealed((v) => !v)}>
              {revealed ? "隠す" : "表示"}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => navigator.clipboard?.writeText(handoff.cookie_value)}
            >
              コピー
            </button>
          </div>
          <ol className="steps">
            <li>
              <a
                href={handoff.confirm_url.replace(/\/cart\/confirm$/, "")}
                target="_blank"
                rel="noreferrer"
              >
                dollyteria.com
              </a>{" "}
              を開く
            </li>
            <li>
              DevTools（F12）→ Application → Cookies → <code>https://www.dollyteria.com</code>
            </li>
            <li>
              <code>{handoff.cookie_name}</code> の値を、上の値に貼り替える（無ければ新規追加）
            </li>
            <li>
              <code>/cart/confirm</code> を開く（再読み込み）→ カートが表示される
            </li>
            <li>内容を確認して「購入する」を自分で押す</li>
          </ol>
        </>
      )}
      <div className="banner warn">
        <b>注意:</b>{" "}
        これはログイン済みの生きたセッションです。早めに開いて購入まで進めてください（時間が経つと無効になります）。この画面を閉じると値は消えます。
      </div>
    </section>
  );
}
