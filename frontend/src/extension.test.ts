import { isExtensionInstalled, openConfirmation } from "./extension";

afterEach(() => {
  delete document.documentElement.dataset.pickupExtension;
});

describe("isExtensionInstalled", () => {
  it("is false without the marker", () => {
    expect(isExtensionInstalled()).toBe(false);
  });

  it("is true when the extension set the marker", () => {
    document.documentElement.dataset.pickupExtension = "1";
    expect(isExtensionInstalled()).toBe(true);
  });
});

describe("openConfirmation", () => {
  it("dispatches a pickup-handoff event carrying the cookie value", () => {
    const events: CustomEvent[] = [];
    const listener = (event: Event) => events.push(event as CustomEvent);
    window.addEventListener("pickup-handoff", listener);

    openConfirmation("sess-xyz");

    window.removeEventListener("pickup-handoff", listener);
    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ cookieValue: "sess-xyz" });
  });
});
