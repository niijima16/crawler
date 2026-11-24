import { useEffect, useRef, useState } from "react";
import { openHandoffStream } from "../api";
import type { Handoff, PreviewStepName } from "../types";

const STEPS: { name: PreviewStepName; label: string }[] = [
  { name: "login", label: "ログイン" },
  { name: "cart", label: "カートに追加" },
  { name: "shipping", label: "配送（店頭受取）を選択" },
  { name: "confirm", label: "確認画面を生成" },
  { name: "handoff", label: "引き継ぎを準備" },
];

type StepState = { status: "active" | "done"; attempt: number };

type Props = {
  accountId: string;
  productId: number;
  paymentMethod: string;
  extensionInstalled: boolean;
  onReady: (handoff: Handoff) => void;
  onClose: () => void;
  /** 新着通知から自動で開いた引き継ぎ（サーバーに長く粘らせる） */
  auto?: boolean;
  /** 自動の引き継ぎを何回目に始め直したか（1 が最初） */
  attempt?: number;
  /** 順番待ちの新着通知の件数 */
  queued?: number;
  onError?: (reason: string) => void;
};

export function HandoffProgress({
  accountId,
  productId,
  paymentMethod,
  extensionInstalled,
  onReady,
  onClose,
  auto = false,
  attempt = 1,
  queued = 0,
  onError,
}: Props) {
  const [states, setStates] = useState<Partial<Record<PreviewStepName, StepState>>>({});
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    const source = openHandoffStream(
      { account_id: accountId, product_id: productId, payment_method: paymentMethod, auto },
      {
        onStep: (step) =>
          setStates((prev) => ({
            ...prev,
            [step.step]: {
              status: step.status === "done" ? "done" : "active",
              attempt: step.attempt,
            },
          })),
        onDone: (handoff) => {
          setFinished(true);
          onReadyRef.current(handoff);
        },
        onError: (reason) => {
          setError(reason);
          onErrorRef.current?.(reason);
        },
      },
    );
    return () => source.close();
  }, [accountId, productId, paymentMethod, auto]);

  return (
    <section className="card" aria-label="確認画面への引き継ぎ">
      <div className="ch">
        <span className="step">▶</span>
        <h2>確認画面への引き継ぎ</h2>
      </div>
      <ul className="prog">
        {STEPS.map(({ name, label }) => {
          const state = states[name];
          const cls = state?.status ?? (error ? "stopped" : "wait");
          const icon = state?.status === "done" ? "✔" : state?.status === "active" ? "⌛" : "·";
          return (
            <li key={name} className={cls}>
              <span className="ico">{icon}</span> {label}
              {state?.status === "active" && state.attempt > 1 && (
                <span className="retry">再試行 {state.attempt}</span>
              )}
            </li>
          );
        })}
      </ul>
      {attempt > 1 && (
        <div className="banner warn">混雑のため、引き継ぎをやり直しています（{attempt}回目）</div>
      )}
      {queued > 0 && (
        <div className="banner warn">
          順番待ち: {queued}件（この引き継ぎが終わったら次を開きます）
        </div>
      )}
      {error ? (
        <div className="banner err">
          引き継ぎに失敗しました（{error}）。もう一度お試しください。
        </div>
      ) : finished ? (
        <div className="banner ok">
          {extensionInstalled
            ? "確認画面をブラウザで開きました。内容を確認し、同意のうえ「する」を押してください。"
            : "引き継ぎの準備ができました。拡張機能を入れると確認画面を自動で開けます。"}
        </div>
      ) : null}
      <div className="row" style={{ marginTop: "10px" }}>
        <button type="button" onClick={onClose}>
          閉じる
        </button>
      </div>
    </section>
  );
}
