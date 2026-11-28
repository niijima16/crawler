export function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  return `${local.slice(0, 1)}***@${domain}`;
}

/** 次の時刻までの残りを「1 時間 23 分」の形にする。 */
export function formatRemaining(targetIso: string, now: Date): string {
  const minutes = Math.floor((new Date(targetIso).getTime() - now.getTime()) / 60_000);
  if (minutes < 1) return "まもなく";
  const hours = Math.floor(minutes / 60);
  return hours === 0 ? `${minutes} 分` : `${hours} 時間 ${minutes % 60} 分`;
}

const WORKER_ALIVE_MS = 3 * 60_000;

/** ワーカーは約60秒ごとに心拍を記録する（最大5分間隔）。3分以上途絶えていたら停止の可能性。 */
export function workerState(
  lastTickIso: string | null,
  now: Date,
): "running" | "stale" | "unknown" {
  if (lastTickIso === null) return "unknown";
  return now.getTime() - new Date(lastTickIso).getTime() <= WORKER_ALIVE_MS ? "running" : "stale";
}
