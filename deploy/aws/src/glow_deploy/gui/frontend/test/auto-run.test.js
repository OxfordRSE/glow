// Deliberately does NOT import test-env.js: __TEST__ stays unset here, so
// this exercises the actual browser code path (`if (!__TEST__) init();`
// firing on import), not the explicit init()-call path the other test files
// use. Guards against a flipped `!` silently going green everywhere else.
import { test } from "node:test";
import assert from "node:assert/strict";
import { freshWindow, teardown } from "./dom-setup.js";

test("without __TEST__ set, importing the module runs init() itself", async () => {
  const window = freshWindow();
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push([url, opts]);
    return { ok: true };
  };

  await import("../test-build/heartbeat.js");
  await null; // let the fire-and-forget ping() promise settle

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/heartbeat");
  assert.equal(calls[0][1].method, "POST");

  teardown(window);
});
