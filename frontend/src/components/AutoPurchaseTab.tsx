import { useState } from "react";
import { ApiError, api } from "../api";
import { formatRemaining, workerState } from "../format";
import { favoriteError } from "../messages";
import type { AppNotification, AutoStatus, NotificationList } from "../types";

type Props = {
  status: AutoStatus | null;
  notifications: NotificationList;
  now: Date;
  onChanged: () => void;
  onOpenConfirmation: (note: AppNotification) => void;
};

const WORKER_TEXT = {
  running: { text: "稼働中", className: "ok" },
  stale: { text: "停止している可能性があります", className: "err" },
  unknown: { text: "未確認", className: "" },
};

export function AutoPurchaseTab({
  status,
  notifications,
  now,
  onChanged,
  onOpenConfirmation,
}: Props) {
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(favoriteError(caught instanceof ApiError ? caught.kind : "network"));
    }
  }

  if (status === null) {
    return (
      <section className="card" aria-label="自動購入">
        <p className="muted">読み込み中…</p>
      </section>
    );
  }
  const worker = WORKER_TEXT[workerState(status.last_tick_at, now)];
  return (
    <section aria-label="自動購入" className="stack">
      <div className="card">
        <div className="ch">
          <span className="step">1</span>
          <h2>稼働状態</h2>
        </div>
        <div className="statgrid">
          <div className="stat">
            <div className="k">次の 21:00（JST）まで</div>
            <div className="v">{formatRemaining(status.next_nightly_at, now)}</div>
          </div>
          <div className="stat">
            <div className="k">監視ワーカー</div>
            <div className={`v ${worker.className}`}>{worker.text}</div>
          </div>
          <div className="stat">
            <div className="k">注文確定の許可（サーバー）</div>
            <div className={`v ${status.order_submit_allowed ? "ok" : "err"}`}>
              {status.order_submit_allowed ? "有効" : "無効"}
            </div>
          </div>
        </div>
        {!status.order_submit_allowed && (
          <div className="banner warn">
            <b>注文確定が無効になっています。</b>{" "}
            購入可能を検知しても購入せず、通知のみ行います。サーバーの設定（ALLOW_ORDER_SUBMIT）で許可してください。
          </div>
        )}
        <label className="row gap-top between">
          <span>
            <b>自動購入</b>
            <span className="muted block">OFF の間は、購入可能を検知しても購入しません</span>
          </span>
          <input
            type="checkbox"
            role="switch"
            aria-label="自動購入"
            checked={status.enabled}
            aria-checked={status.enabled}
            onChange={() => run(() => api.setAutoEnabled(!status.enabled))}
          />
        </label>
        <p className="hint">
          1 分ごとの監視と、毎晩 21:00 の確認を行います。1 分ごとの監視の中身は表示しません。
        </p>
      </div>
      <div className="card">
        <div className="ch">
          <span className="step">2</span>
          <h2>購入結果の通知</h2>
          {notifications.unread > 0 && (
            <span className="chip err">未読 {notifications.unread}</span>
          )}
        </div>
        {notifications.items.length === 0 ? (
          <p className="empty">通知はまだありません</p>
        ) : (
          <ul className="loglist">
            {notifications.items.map((note) => (
              <li key={note.id} className={`log${note.read ? "" : " unread"}`}>
                <span className="dot" />
                <div>
                  <div>{note.message}</div>
                  {note.kind === "new_arrival" && note.product_id !== null && (
                    <div className="row" style={{ marginTop: "6px" }}>
                      <button
                        type="button"
                        className="dark"
                        onClick={() => onOpenConfirmation(note)}
                      >
                        確認画面を開く
                      </button>
                    </div>
                  )}
                  <div className="t">{new Date(note.created_at).toLocaleString("ja-JP")}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="row gap-top">
          <button
            type="button"
            className="secondary"
            disabled={notifications.unread === 0}
            onClick={() => run(() => api.markNotificationsRead())}
          >
            すべて既読にする
          </button>
        </div>
      </div>
      {error && <div className="banner err">{error}</div>}
    </section>
  );
}
