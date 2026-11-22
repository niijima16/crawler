import type { ApiErrorKind } from "./api";

export const LOGIN_FAILED =
  "ログインに失敗しました。メールアドレスとパスワードを確認してください。";
export const LOGIN_INVALIDATED =
  "ログイン情報が無効になりました。パスワードが変更された可能性があります。アカウントを再登録してください。";

export function searchError(kind: ApiErrorKind): string {
  if (kind === "not_found") return "その商品は見つかりません。";
  return "サイトに接続できません。時間をおいて再度お試しください。";
}

export function runError(kind: ApiErrorKind): { title: string; detail: string } {
  switch (kind) {
    case "not_found":
      return { title: "商品が見つかりません。", detail: "商品 ID を確認してください。" };
    case "not_purchasable":
      return { title: "この商品は購入できません。", detail: "売り切れの可能性があります。" };
    case "payment_unavailable":
      return {
        title: "選んだ支払方法は、この商品では選べません。",
        detail: "オプションで別の支払方法を選んでください。",
      };
    case "timeout":
      return {
        title: "時間内に確認画面へ進めませんでした。",
        detail: "サイトが混雑しています。しばらくしてから再度お試しください。",
      };
    case "disabled":
      return {
        title: "注文確定は無効になっています。",
        detail:
          "サーバーの設定（ALLOW_ORDER_SUBMIT）で許可されていません。実行モードを「確認画面まで」に戻してください。",
      };
    case "unsupported":
    case "invalid":
      return {
        title: "この組み合わせでは実行できません。",
        detail: "オプションの支払方法と実行モードを確認してください。",
      };
    default:
      return {
        title: "サイトに接続できません。",
        detail: "時間をおいて再度お試しください。",
      };
  }
}

export function favoriteError(kind: ApiErrorKind): string {
  switch (kind) {
    case "duplicate":
      return "この商品はすでにお気に入りに入っています。";
    case "limit":
      return "お気に入りは 20 件までです。解除してから登録してください。";
    case "unsupported":
      return "この支払方法では自動購入できません。店頭支払・代金引換・銀行振込・郵便振替を選んでください。";
    case "not_found":
      return "商品またはアカウントが見つかりません。";
    case "invalid_transition":
      return "購入処理中のため、この操作はできません。";
    default:
      return "サイトに接続できません。時間をおいて再度お試しください。";
  }
}

export function accountError(kind: ApiErrorKind): string {
  switch (kind) {
    case "login_failed":
      return `${LOGIN_FAILED}追加されていません。`;
    case "duplicate":
      return "このメールアドレスのアカウントはすでに登録されています。";
    default:
      return "サイトに接続できません。時間をおいて再度お試しください。";
  }
}
