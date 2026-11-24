// 専用のブラウザ拡張との受け渡し。拡張は、ツール画面に目印を置き、pickup-handoff を受けて
// PHPSESSID をセットし /cart/confirm のタブを開く（ボタンは押さない）。
const MARKER = "pickupExtension";
export const HANDOFF_EVENT = "pickup-handoff";

export function isExtensionInstalled(): boolean {
  return document.documentElement.dataset[MARKER] === "1";
}

export function openConfirmation(cookieValue: string): void {
  window.dispatchEvent(new CustomEvent(HANDOFF_EVENT, { detail: { cookieValue } }));
}
