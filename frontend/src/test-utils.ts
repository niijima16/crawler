import { vi } from "vitest";

export type Handler = (url: URL, init: RequestInit | undefined) => Response | Promise<Response>;

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** `fetch` を、"METHOD /path" をキーにしたハンドラで置き換える。呼び出しは `calls` に残る。 */
export function mockApi(handlers: Record<string, Handler>) {
  const calls: { key: string; url: URL; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    calls.push({ key, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected request: ${key}`);
    return handler(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}
