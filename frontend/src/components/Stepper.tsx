const STEPS = ["ログイン", "オプション", "商品を選ぶ", "ご注文内容", "結果"];

export function Stepper({ current }: { current: number }) {
  return (
    <ol className="stepper">
      {STEPS.map((name, index) => {
        const n = index + 1;
        const state = n === current ? "cur" : n < current ? "done" : "";
        return (
          <li key={name} className={`s ${state}`} aria-current={n === current ? "step" : undefined}>
            {n}. {name}
          </li>
        );
      })}
    </ol>
  );
}
