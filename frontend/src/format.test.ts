import { formatRemaining, maskEmail, workerState } from "./format";

describe("maskEmail", () => {
  it("hides the local part", () => {
    expect(maskEmail("tester@dollyteria")).toBe("t***@dollyteria");
  });
});

describe("formatRemaining", () => {
  const now = new Date("2026-11-22T11:00:00Z");

  it.each([
    ["2026-11-22T12:23:00Z", "1 時間 23 分"],
    ["2026-11-22T11:45:00Z", "45 分"],
    ["2026-11-22T11:00:30Z", "まもなく"],
    ["2026-11-23T11:00:00Z", "24 時間 0 分"],
  ])("formats %s as %s", (target, expected) => {
    expect(formatRemaining(target, now)).toBe(expected);
  });
});

describe("workerState", () => {
  const now = new Date("2026-11-22T11:00:00Z");

  it("is running when the last tick is recent", () => {
    expect(workerState("2026-11-22T10:58:30Z", now)).toBe("running");
  });

  it("is stale when the last tick is old", () => {
    expect(workerState("2026-11-22T10:40:00Z", now)).toBe("stale");
  });

  it("is unknown before the first tick", () => {
    expect(workerState(null, now)).toBe("unknown");
  });
});
