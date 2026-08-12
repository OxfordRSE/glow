import "./test-env.js";
import { test } from "node:test";
import assert from "node:assert/strict";
import { freshWindow, teardown } from "./dom-setup.js";
import { init } from "../test-build/domain-check.js";

function wait(window, ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setup() {
  document.body.innerHTML = `
    <input id="domain-input">
    <div id="cert-arn-field"><input id="certificate-arn-input"></div>
    <div id="auto-dns-notice" hidden></div>
  `;
}

function setValueAndFireInput(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input"));
}

test("debounces the domain check: no fetch until the input settles", async () => {
  const window = freshWindow();
  setup();
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return { ok: true, json: async () => ({ auto: true }) };
  };

  init();
  setValueAndFireInput(window, document.getElementById("domain-input"), "example.com");
  assert.equal(calls, 0);
  await wait(window, 500);
  assert.equal(calls, 1);

  teardown(window);
});

test("auto=true hides the cert field, clears any pasted ARN, and shows the notice", async () => {
  const window = freshWindow();
  setup();
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ auto: true }) });
  document.getElementById("certificate-arn-input").value = "arn:aws:acm:...";

  init();
  setValueAndFireInput(window, document.getElementById("domain-input"), "example.com");
  await wait(window, 500);

  assert.equal(document.getElementById("cert-arn-field").hidden, true);
  assert.equal(document.getElementById("certificate-arn-input").value, "");
  assert.equal(document.getElementById("auto-dns-notice").hidden, false);

  teardown(window);
});

test("auto=false leaves the cert field visible and hides the notice", async () => {
  const window = freshWindow();
  setup();
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ auto: false }) });

  init();
  setValueAndFireInput(window, document.getElementById("domain-input"), "example.com");
  await wait(window, 500);

  assert.equal(document.getElementById("cert-arn-field").hidden, false);
  assert.equal(document.getElementById("auto-dns-notice").hidden, true);

  teardown(window);
});

test("clearing the input hides the notice immediately, without a fetch", async () => {
  const window = freshWindow();
  setup();
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return { ok: true, json: async () => ({ auto: true }) };
  };

  init();
  setValueAndFireInput(window, document.getElementById("domain-input"), "");

  assert.equal(document.getElementById("auto-dns-notice").hidden, true);
  await wait(window, 500);
  assert.equal(calls, 0);

  teardown(window);
});

test("a non-ok response is treated as auto=false, not an error", async () => {
  const window = freshWindow();
  setup();
  globalThis.fetch = async () => ({ ok: false });

  init();
  setValueAndFireInput(window, document.getElementById("domain-input"), "example.com");
  await wait(window, 500);

  assert.equal(document.getElementById("cert-arn-field").hidden, false);
  assert.equal(document.getElementById("auto-dns-notice").hidden, true);

  teardown(window);
});

test("a slow in-flight response is discarded once the domain has changed again", async () => {
  const window = freshWindow();
  setup();
  globalThis.fetch = async (url) => {
    const domain = new URL(url, "http://localhost").searchParams.get("domain");
    if (domain === "slow.com") {
      await wait(window, 300);
      return { ok: true, json: async () => ({ auto: true }) };
    }
    return { ok: true, json: async () => ({ auto: false }) };
  };

  init();
  const input = document.getElementById("domain-input");
  setValueAndFireInput(window, input, "slow.com");
  await wait(window, 500); // debounce fires; slow.com fetch starts (300ms to resolve)
  setValueAndFireInput(window, input, "fast.com");
  await wait(window, 500); // debounce fires again; fast.com resolves right away
  await wait(window, 400); // give the slow.com response a chance to land too, if it's going to

  // fast.com's auto:false should win — slow.com's late auto:true must be discarded.
  assert.equal(document.getElementById("cert-arn-field").hidden, false);
  assert.equal(document.getElementById("auto-dns-notice").hidden, true);

  teardown(window);
});
