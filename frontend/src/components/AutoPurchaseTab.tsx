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
  autoOpen: boolean;
  onAutoOpenChange: (on: boolean) => void;
  /** 自動で開いた引き継ぎの最新の状態（1行） */
  autoLine?: AutoLine | null;
  /** 自動の引き継ぎの実行中（手動の「確認画面を開く」を押せなくする） */
  manualBlocked?: boolean;
};

export type AutoLine = { text: string; tone: "ok" | "warn" | "err" };

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
  autoOpen,
  onAutoOpenChange,
  autoLine = null,
  manualBlocked = false,
}: Props) {
  const [error, setError] = useState<string | null>(null);
  const [confirmingDeleteAll, setConfirmingDeleteAll] = useState(false);

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
      <section className="card" aria-label="自動">
        <p className="muted">読み込み中…</p>
      </section>
    );
  }
  const worker = WORKER_TEXT[workerState(status.last_tick_at, now)];
  return (
    <section aria-label="自動" className="stack">
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
            可能を検知してもせず、通知のみ行います。サーバーの設定（ALLOW_ORDER_SUBMIT）で許可してください。
          </div>
        )}
        <label className="row gap-top between">
          <span>
            <b>自動</b>
            <span className="muted block">OFF の間は、可能を検知してもしません</span>
          </span>
          <input
            type="checkbox"
            role="switch"
            aria-label="自動"
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
          <h2>結果の通知</h2>
          {notifications.unread > 0 && (
            <span className="chip err">未読 {notifications.unread}</span>
          )}
        </div>
        <label className="row between">
          <span>
            <b>新着通知で自動で確認画面を開く</b>
            <span className="muted block">
              ON
              の間、新着通知が届いたら（画面を開いたときの未読も）自動で引き継ぎを始めます。進捗は表示せず、下に1行だけ結果を出します。同時に動かすのは1件だけで、ほかは順番待ち（新しい順）。確認画面まで届いたらすぐ次を開きます（前に開いた確認画面は使えなくなることがあります）。混雑で失敗したら売り切れるまでやり直します。止めるときは
              OFF
              にしてください（実行中の引き継ぎも止まります）。この画面を開いたままにしてください。
            </span>
          </span>
          <input
            type="checkbox"
            role="switch"
            aria-label="新着通知で自動で確認画面を開く"
            checked={autoOpen}
            aria-checked={autoOpen}
            onChange={() => onAutoOpenChange(!autoOpen)}
          />
        </label>
        {autoLine && <div className={`banner ${autoLine.tone}`}>{autoLine.text}</div>}
        {notifications.items.length === 0 ? (
          <p className="empty">通知はまだありません</p>
        ) : (
          <ul className="loglist">
            {notifications.items.map((note) => (
              <li key={note.id} className={`log${note.read ? "" : " unread"}`}>
                <span className="dot" />
                <div>
                  <div>{note.message}</div>
                  <div className="row" style={{ marginTop: "6px" }}>
                    {note.kind === "new_arrival" && note.product_id !== null && (
                      <button
                        type="button"
                        className="dark"
                        disabled={manualBlocked}
                        onClick={() => onOpenConfirmation(note)}
                      >
                        確認画面を開く
                      </button>
                    )}
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => run(() => api.deleteNotification(note.id))}
                    >
                      削除
                    </button>
                  </div>
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
          {confirmingDeleteAll ? (
            <div className="push row">
              <span className="muted">通知をすべて削除します</span>
              <button
                type="button"
                className="danger"
                onClick={() => {
                  setConfirmingDeleteAll(false);
                  run(() => api.deleteAllNotifications());
                }}
              >
                削除する
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setConfirmingDeleteAll(false)}
              >
                やめる
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="secondary"
              disabled={notifications.items.length === 0}
              onClick={() => setConfirmingDeleteAll(true)}
            >
              すべて削除
            </button>
          )}
        </div>
      </div>
      {error && <div className="banner err">{error}</div>}
    </section>
  );
}
