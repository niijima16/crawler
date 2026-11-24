// 新着通知（キーワードお気に入り）から、確認画面を自動で開くための判定。
// 同時に動かす引き継ぎは1件だけ（ブラウザはサイトのセッションを1つしか持てない）なので、待ち行列で順番に開く。
import type { AppNotification } from "./types";

const STORAGE_KEY = "pickup.autoOpenArrival";

/** 確認画面を開ける新着通知（商品IDがある） */
export type Arrival = AppNotification & { product_id: number };

const isArrival = (note: AppNotification): note is Arrival =>
  note.kind === "new_arrival" && note.product_id !== null;

const newestFirst = (a: AppNotification, b: AppNotification) =>
  b.created_at.localeCompare(a.created_at);

/**
 * 取得した通知から、待ち行列に足す新着通知（新しい順）と、既知の通知IDを返す。
 * seen が null（画面を開いて最初の取得）のときは、未読の新着通知を対象にする。
 */
export function collectArrivals(
  items: AppNotification[],
  seen: Set<string> | null,
): { arrivals: Arrival[]; seen: Set<string> } {
  const fresh = items.filter((note) => (seen === null ? !note.read : !seen.has(note.id)));
  return {
    arrivals: fresh.filter(isArrival).sort(newestFirst),
    seen: new Set([...(seen ?? []), ...items.map((note) => note.id)]),
  };
}

/** 待ち行列に足す（新しい順。同じ商品はすでにあれば足さない）。 */
export function enqueue(queue: Arrival[], arrivals: Arrival[]): Arrival[] {
  const queued = new Set(queue.map((note) => note.product_id));
  const added = arrivals.filter((note) => !queued.has(note.product_id));
  return [...queue, ...added].sort(newestFirst);
}

export function loadAutoOpen(): boolean {
  return localStorage.getItem(STORAGE_KEY) === "1";
}

export function saveAutoOpen(on: boolean): void {
  localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
}
