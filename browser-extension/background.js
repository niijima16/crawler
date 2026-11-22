// 受け取ったセッション（PHPSESSID）を dollyteria.com にセットし、確認画面のタブを開く。
// 「購入する」のクリックや reCAPTCHA への操作はしない（ユーザーが手動で押す）。
const CONFIRM_URL = "https://www.dollyteria.com/cart/confirm";

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== "open-confirmation" || typeof message.cookieValue !== "string") {
    return;
  }
  chrome.cookies.set(
    {
      url: CONFIRM_URL,
      name: "PHPSESSID",
      value: message.cookieValue,
      path: "/",
      secure: true,
      httpOnly: true,
      sameSite: "no_restriction",
    },
    () => {
      chrome.tabs.create({ url: CONFIRM_URL });
    },
  );
});
