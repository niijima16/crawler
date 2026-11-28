// 確認画面（/cart/confirm）で、同意チェックと「する」を見つけやすくする。
// チェックは入れない・ボタンは押さない（ユーザーが自分で行う）。表示を助けるだけ。
// 混雑（503）などで確認画面が出ていないときは、background にリロードを依頼する（GETの再読み込みのみ）。
(() => {
  const consent = document.querySelector("#policy_agree");
  const buy = document.querySelector('input[name="go-next"]');
  const ready = Boolean(consent || buy);

  if (ready) {
    const highlight = (el) => {
      if (!el) {
        return;
      }
      const box = el.closest("label, span, div, td, th") || el;
      box.style.outline = "3px solid #f08c00";
      box.style.outlineOffset = "2px";
      box.style.borderRadius = "6px";
      box.style.transition = "outline-color 1s ease";
    };
    highlight(consent);
    highlight(buy);
    (consent || buy).scrollIntoView({ behavior: "smooth", block: "center" });
    // 成功。自動リロードを止める。
    chrome.runtime.sendMessage({ type: "confirm-ready" });
    return;
  }

  // 確認画面の目印が無い＝混雑/503。background に再読み込みを依頼し、状況を表示する。
  chrome.runtime.sendMessage({ type: "confirm-busy" }, (res) => {
    showNotice(Boolean(res && res.retrying));
  });

  function showNotice(retrying) {
    const id = "pickup-busy-notice";
    document.getElementById(id)?.remove();
    const bar = document.createElement("div");
    bar.id = id;
    bar.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:2147483647;padding:10px 14px;" +
      "background:#fff1dc;color:#a15c00;font:14px system-ui,sans-serif;text-align:center;" +
      "box-shadow:0 2px 6px rgba(0,0,0,.2)";
    if (retrying) {
      bar.textContent = "混雑（503）のため、確認画面を自動で再読み込みしています…";
    } else {
      bar.textContent = "確認画面を開けませんでした（混雑）。";
      const button = document.createElement("button");
      button.textContent = "再試行";
      button.style.cssText =
        "margin-left:10px;padding:4px 12px;border:0;border-radius:6px;" +
        "background:#f08c00;color:#1b1200;font-weight:600;cursor:pointer";
      button.addEventListener("click", () => location.reload());
      bar.appendChild(button);
    }
    document.body?.appendChild(bar);
  }
})();
