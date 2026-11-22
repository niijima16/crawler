// 確認画面（/cart/confirm）で、同意チェックと「購入する」を見つけやすくする。
// チェックは入れない・購入ボタンは押さない（ユーザーが自分で行う）。表示を助けるだけ。
(() => {
  const consent = document.querySelector("#policy_agree");
  const buy = document.querySelector('input[name="go-next"]');
  if (!consent && !buy) {
    return;
  }
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
})();
