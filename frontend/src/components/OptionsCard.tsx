import type { PaymentMethod } from "../types";
import { Segmented } from "./Segmented";

export type Mode = "check" | "order" | "handoff";
export type SearchMode = "code" | "partial";

type Props = {
  methods: PaymentMethod[];
  paymentId: string;
  mode: Mode;
  searchMode: SearchMode;
  disabled: boolean;
  onPayment: (id: string) => void;
  onMode: (mode: Mode) => void;
  onSearchMode: (mode: SearchMode) => void;
};

export function OptionsCard({
  methods,
  paymentId,
  mode,
  searchMode,
  disabled,
  onPayment,
  onMode,
  onSearchMode,
}: Props) {
  const selected = methods.find((m) => m.id === paymentId);
  const submitBlocked = selected !== undefined && !selected.submit_supported;
  return (
    <section className={`card${mode === "order" ? " order" : ""}`} aria-label="オプション">
      <div className="ch">
        <span className="step">2</span>
        <h2>オプション</h2>
        <span className={`chip${mode === "order" ? " err" : ""}`}>
          {mode === "order" ? "注文確定モード" : "選択系はここに集約"}
        </span>
      </div>
      <div className="grid3">
        <div className="opt">
          実行モード
          <Segmented
            label="実行モード"
            value={mode}
            disabled={disabled}
            onChange={onMode}
            options={[
              { value: "check", label: "確認画面まで" },
              { value: "order", label: "注文確定まで", disabled: submitBlocked, danger: true },
              { value: "handoff", label: "ブラウザで", disabled: !selected?.preview_supported },
            ]}
          />
        </div>
        <label className="opt">
          支払方法
          <select
            aria-label="支払方法"
            value={paymentId}
            disabled={disabled}
            onChange={(event) => onPayment(event.target.value)}
          >
            {methods.map((method) => (
              <option key={method.id} value={method.id} disabled={!method.preview_supported}>
                {method.preview_supported ? method.label : `${method.label}（未対応）`}
              </option>
            ))}
          </select>
        </label>
        <div className="opt">
          検索方式
          <Segmented
            label="検索方式"
            value={searchMode}
            disabled={disabled}
            onChange={onSearchMode}
            options={[
              { value: "code", label: "コード" },
              { value: "partial", label: "部分一致" },
            ]}
          />
        </div>
      </div>
      <p className="hint">クレジットカードは、ブラウザでのカード情報入力が必要なため未対応です。</p>
      {submitBlocked && (
        <p className="hint">
          {selected.label}は外部の決済・審査を伴うため、注文確定は選べません（確認画面までのみ）。
        </p>
      )}
      {mode === "order" && (
        <div className="banner order">
          <b>注文確定モード</b> — 実行すると「する」を 1
          回送信します（取り消しにくい操作）。実行前に確認ダイアログが出ます。
        </div>
      )}
    </section>
  );
}
