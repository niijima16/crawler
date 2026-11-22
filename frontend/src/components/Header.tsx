import { maskEmail } from "../format";

export function Header({ email }: { email: string | null }) {
  return (
    <header className="hdr">
      <div className="brand">
        <span className="logo">P</span>
        Pickup Assistant
      </div>
      <span className="sp" />
      <span className="acct">
        <span className={email ? "dot" : "dot off"} />
        {email ? maskEmail(email) : "未ログイン"}
      </span>
    </header>
  );
}
