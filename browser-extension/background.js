// 受け取ったセッション（PHPSESSID）を dollyteria.com にセットし、確認画面のタブを開く。
// 開いた確認画面が 503/読み込み失敗のときは、そのタブを自動で再読み込みする
// （間隔 0.1秒＋ゆらぎ最大0.5秒・開始から約3分まで）。再読み込みは GET のみ。
const CONFIRM_URL = "https://www.dollyteria.com/cart/confirm";
const RETRY_BUDGET_MS = 180_000;

// このタブは「引き継ぎで開いたタブ」。値は開始時刻（ms）。混雑リロードの対象。
const managed = {};

function nextDelayMs() {
  return (0.1 + Math.random() * 0.5) * 1000;
}

function withinBudget(tabId) {
  const started = managed[tabId];
  return started !== undefined && Date.now() - started < RETRY_BUDGET_MS;
}

function scheduleReload(tabId) {
  setTimeout(() => chrome.tabs.reload(tabId), nextDelayMs());
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "open-confirmation" && typeof message.cookieValue === "string") {
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
        chrome.tabs.create({ url: CONFIRM_URL }, (tab) => {
          if (tab?.id !== undefined) {
            managed[tab.id] = Date.now();
          }
        });
      },
    );
    return;
  }

  const tabId = sender.tab?.id;
  if (message?.type === "confirm-ready") {
    if (tabId !== undefined) {
      delete managed[tabId]; // 成功。以後はリロードしない。
    }
    return;
  }
  if (message?.type === "confirm-busy") {
    const retrying = tabId !== undefined && withinBudget(tabId);
    if (retrying) {
      scheduleReload(tabId);
    } else if (tabId !== undefined) {
      delete managed[tabId]; // 時間切れ。手動の再試行に委ねる。
    }
    sendResponse({ retrying });
    return true; // 非同期応答
  }
});

// 読み込み自体が失敗したとき（本文が無く content script が動かない）も、対象タブなら再読み込みする。
chrome.webNavigation.onErrorOccurred.addListener((details) => {
  if (details.frameId !== 0) {
    return;
  }
  if (withinBudget(details.tabId)) {
    scheduleReload(details.tabId);
  }
});

// 対象タブが閉じられたら掃除する。
chrome.tabs.onRemoved.addListener((tabId) => {
  delete managed[tabId];
});
