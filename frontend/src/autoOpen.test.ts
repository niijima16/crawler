import { collectArrivals, enqueue, loadAutoOpen, saveAutoOpen } from "./autoOpen";
import { NOTE_NEW_ARRIVAL, NOTE_REJECTED } from "./test-data";
import type { AppNotification } from "./types";

const arrival = (id: string, productId: number, createdAt: string, read = false) =>
  ({
    ...NOTE_NEW_ARRIVAL,
    id,
    product_id: productId,
    created_at: createdAt,
    read,
  }) satisfies AppNotification;

const OLD = arrival("a1", 1, "2026-11-25T12:00:00Z");
const NEW = arrival("a2", 2, "2026-11-25T12:00:05Z");
const READ = arrival("a3", 3, "2026-11-25T12:00:09Z", true);
const NO_PRODUCT = { ...arrival("a4", 4, "2026-11-25T12:00:10Z"), product_id: null };

describe("collectArrivals", () => {
  it("on the first load, returns unread new arrivals with a product, newest first", () => {
    const { arrivals, seen } = collectArrivals([OLD, READ, NOTE_REJECTED, NEW, NO_PRODUCT], null);

    expect(arrivals.map((n) => n.id)).toEqual(["a2", "a1"]);
    expect([...seen].sort()).toEqual(["a1", "a2", "a3", "a4", NOTE_REJECTED.id].sort());
  });

  it("afterwards, returns only notifications not seen yet (read or not)", () => {
    const first = collectArrivals([OLD], null);

    const { arrivals, seen } = collectArrivals([READ, NEW, OLD], first.seen);

    expect(arrivals.map((n) => n.id)).toEqual(["a3", "a2"]);
    expect(seen.has("a3") && seen.has("a2") && seen.has("a1")).toBe(true);
  });
});

describe("enqueue", () => {
  it("keeps the queue newest first and skips products already queued", () => {
    const queue = enqueue([OLD], [NEW, arrival("a5", 1, "2026-11-25T12:00:20Z")]);

    expect(queue.map((n) => n.id)).toEqual(["a2", "a1"]);
  });
});

describe("auto open switch", () => {
  afterEach(() => localStorage.clear());

  it("is off by default and remembers the choice", () => {
    expect(loadAutoOpen()).toBe(false);

    saveAutoOpen(true);
    expect(loadAutoOpen()).toBe(true);

    saveAutoOpen(false);
    expect(loadAutoOpen()).toBe(false);
  });
});
