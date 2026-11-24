export type Tab = "search" | "favorites" | "auto";

type Props = { current: Tab; unread: number; onChange: (tab: Tab) => void };

const TABS: { id: Tab; label: string }[] = [
  { id: "search", label: "商品を探す" },
  { id: "favorites", label: "お気に入り" },
  { id: "auto", label: "自動" },
];

export function Tabs({ current, unread, onChange }: Props) {
  return (
    <div className="tabs" role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={tab.id === current}
          className={`tab${tab.id === current ? " cur" : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.id === "auto" && unread > 0 && <span className="nbadge">{unread}</span>}
        </button>
      ))}
    </div>
  );
}
