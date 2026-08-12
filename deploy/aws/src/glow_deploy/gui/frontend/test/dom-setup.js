// Minimal happy-dom wiring shared by these tests. Source files address
// `window.x` (setTimeout/location/etc) and bare globals (document, fetch,
// HTMLButtonElement...) both — so both need to land on globalThis. Sources
// guard their auto-run wiring behind __TEST__ (see e.g. job-status.ts).
import { Window } from "happy-dom";

export function freshWindow(url = "http://localhost/") {
  const window = new Window({ url });
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.HTMLButtonElement = window.HTMLButtonElement;
  globalThis.HTMLInputElement = window.HTMLInputElement;
  globalThis.Event = window.Event;
  globalThis.requestAnimationFrame = window.requestAnimationFrame.bind(window);
  // Node's own `navigator` global is a read-only accessor — plain assignment throws.
  Object.defineProperty(globalThis, "navigator", {
    value: { clipboard: { writeText: async () => {} } },
    configurable: true,
  });
  // __TEST__ is NOT set here — see test-env.js, the sole owner of that flag.
  // A test exercising the real (unguarded) auto-run path relies on this.
  return window;
}

// Cancels pending timers/fetches on the happy-dom window so a test's
// dangling setInterval doesn't keep the process alive past the test run.
export function teardown(window) {
  window.happyDOM.abort();
}
