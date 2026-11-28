import { type FormEvent, useState } from "react";
import { ApiError, api } from "../api";
import { maskEmail } from "../format";
import { accountError } from "../messages";
import type { Account } from "../types";

type Props = {
  accounts: Account[] | null;
  selectedId: string | null;
  notice: string | null;
  onSelect: (id: string) => void;
  onAdded: (account: Account) => void;
  onDeleted: (id: string) => void;
};

export function AccountCard({ accounts, selectedId, notice, onSelect, onAdded, onDeleted }: Props) {
  const [adding, setAdding] = useState(false);
  const [label, setLabel] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const loading = accounts === null;
  const list = accounts ?? [];
  const showForm = !loading && (list.length === 0 || adding);
  const loggedIn = selectedId !== null;

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const account = await api.addAccount({
        label: label.trim() || email.split("@")[0],
        email,
        password,
      });
      setLabel("");
      setEmail("");
      setPassword("");
      setAdding(false);
      onAdded(account);
    } catch (caught) {
      setError(accountError(caught instanceof ApiError ? caught.kind : "network"));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api.deleteAccount(id);
      setConfirmingId(null);
      onDeleted(id);
    } catch (caught) {
      setError(accountError(caught instanceof ApiError ? caught.kind : "network"));
    }
  }

  const chip = loading ? "読み込み中…" : loggedIn ? "ログイン済み" : "未ログイン";
  return (
    <section className="card" aria-label="アカウント">
      <div className="ch">
        <span className={`step${loggedIn ? " done" : ""}`}>{loggedIn ? "✓" : "1"}</span>
        <h2>アカウント</h2>
        <span className={`chip${loggedIn ? " ok" : " off"}`}>{chip}</span>
      </div>
      {list.length > 0 && (
        <ul className="acctlist">
          {list.map((account) => {
            const current = account.id === selectedId;
            return (
              <li key={account.id} className={`acct-item${current ? " sel" : ""}`}>
                <span className="avatar">{account.label.slice(0, 1)}</span>
                <div>
                  <b>{account.label}</b>
                  <div className="muted">{maskEmail(account.email)}</div>
                </div>
                {current ? (
                  <span className="chip ok push">使用中</span>
                ) : confirmingId === account.id ? (
                  <div className="push row">
                    <span className="muted">このアカウントのお気に入りも削除されます</span>
                    <button type="button" className="danger" onClick={() => remove(account.id)}>
                      削除する
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setConfirmingId(null)}
                    >
                      やめる
                    </button>
                  </div>
                ) : (
                  <div className="push row">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => onSelect(account.id)}
                    >
                      切り替える
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setConfirmingId(account.id)}
                    >
                      削除
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {!loading && list.length > 0 && !adding && (
        <div className="row gap-top">
          <button type="button" className="secondary" onClick={() => setAdding(true)}>
            アカウントを追加
          </button>
        </div>
      )}
      {showForm && (
        <form onSubmit={add}>
          <div className="row gap-top">
            <label className="field">
              ラベル
              <input
                type="text"
                value={label}
                disabled={busy}
                placeholder="例: テスト用 C"
                onChange={(event) => setLabel(event.target.value)}
              />
            </label>
            <label className="field">
              メールアドレス
              <input
                type="email"
                autoComplete="off"
                value={email}
                disabled={busy}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label className="field">
              パスワード
              <input
                type="password"
                autoComplete="off"
                value={password}
                disabled={busy}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
          </div>
          <div className="row gap-top">
            <button type="submit" className="dark" disabled={busy}>
              ログインを確認して追加
            </button>
            <span className="muted">
              サーバーに暗号化して保存します。この画面では再表示されません
            </span>
          </div>
        </form>
      )}
      {(error ?? notice) && <div className="banner err">{error ?? notice}</div>}
    </section>
  );
}
