// ツール画面に注入される。拡張の存在を知らせ、確認画面を開く要求を background に中継する。
// 扱うのはセッション Cookie の受け渡しだけで、「購入する」は押さない。
document.documentElement.dataset.pickupExtension = "1";

window.addEventListener("pickup-handoff", (event) => {
  const cookieValue = event.detail && event.detail.cookieValue;
  if (typeof cookieValue === "string" && cookieValue.length > 0) {
    chrome.runtime.sendMessage({ type: "open-confirmation", cookieValue });
  }
});
