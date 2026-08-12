import { test } from "node:test";
import assert from "node:assert/strict";
import { redact, debugLog } from "../test-build/debug.js";

test("redact leaves non-secret keys untouched", () => {
  assert.deepEqual(redact({ id: "abc123", name: "x" }), { id: "abc123", name: "x" });
});

test("redact masks token/secret/password/credential keys, case-insensitively", () => {
  assert.deepEqual(
    redact({ Token: "t", secret_key: "s", password: "p", credential: "c", account_id: "keep" }),
    { Token: "[redacted]", secret_key: "[redacted]", password: "[redacted]", credential: "[redacted]", account_id: "keep" },
  );
});

test("redact recurses into nested objects and arrays", () => {
  assert.deepEqual(
    redact({ items: [{ token: "t" }, { id: 1 }] }),
    { items: [{ token: "[redacted]" }, { id: 1 }] },
  );
});

test("redact leaves primitives and null untouched", () => {
  assert.equal(redact("plain"), "plain");
  assert.equal(redact(42), 42);
  assert.equal(redact(null), null);
});

test("debugLog forwards the redacted value to console.debug", (t) => {
  const calls = [];
  t.mock.method(console, "debug", (...args) => calls.push(args));
  debugLog("label", { token: "secret", id: 1 });
  assert.deepEqual(calls, [["label", { token: "[redacted]", id: 1 }]]);
});
