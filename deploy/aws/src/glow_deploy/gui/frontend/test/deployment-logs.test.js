import "./test-env.js";
import { test } from "node:test";
import assert from "node:assert/strict";
import { freshWindow, teardown } from "./dom-setup.js";
import { init } from "../test-build/deployment-logs.js";

function wait(window, ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setup() {
  document.body.innerHTML = `
    <p id="status-loading"></p>
    <p id="status-error" hidden></p>
    <div id="status-card" hidden>
      <span id="status-health"></span>
      <span id="status-git-ref"></span>
      <span id="status-git-commit"></span>
    </div>
    <p id="containers-loading"></p>
    <p id="containers-error" hidden></p>
    <div id="containers-section"></div>
  `;
}

test("renders runner status and containers on a successful load", async () => {
  const window = freshWindow("http://localhost/deployments/example.com/logs");
  setup();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      status: { health: "healthy", git_ref: "main", git_commit: "abc123" },
      error: null,
      containers: { "glow-web-1": ["hello"] },
      containers_error: null,
    }),
  });

  init();
  await wait(window, 50);

  assert.equal(document.getElementById("status-loading").hidden, true);
  assert.equal(document.getElementById("status-card").hidden, false);
  assert.equal(document.getElementById("status-health").textContent, "healthy");
  assert.equal(document.getElementById("status-git-ref").textContent, "main");
  assert.equal(document.getElementById("status-git-commit").textContent, "abc123");

  // glow-<name>-<n> containers show just the middle part as the summary label.
  const summary = document.querySelector("#containers-section summary");
  assert.equal(summary.childNodes[0].textContent, "web");

  teardown(window);
});

test("falls back to a de-slugged name for containers that don't match the glow-*-N pattern", async () => {
  const window = freshWindow("http://localhost/deployments/example.com/logs");
  setup();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      status: null,
      error: null,
      containers: { "reverse_proxy": ["hello"] },
      containers_error: null,
    }),
  });

  init();
  await wait(window, 50);

  const summary = document.querySelector("#containers-section summary");
  assert.equal(summary.childNodes[0].textContent, "reverse proxy");

  teardown(window);
});

test("shows the status error message instead of the status card", async () => {
  const window = freshWindow("http://localhost/deployments/example.com/logs");
  setup();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ status: null, error: "SSM agent unreachable", containers: null, containers_error: null }),
  });

  init();
  await wait(window, 50);

  assert.equal(document.getElementById("status-card").hidden, true);
  assert.equal(document.getElementById("status-error").hidden, false);
  assert.equal(document.getElementById("status-error").textContent, "SSM agent unreachable");

  teardown(window);
});

test("shows the containers error message instead of rendering containers", async () => {
  const window = freshWindow("http://localhost/deployments/example.com/logs");
  setup();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ status: null, error: null, containers: null, containers_error: "no containers found" }),
  });

  init();
  await wait(window, 50);

  assert.equal(document.getElementById("containers-error").hidden, false);
  assert.equal(document.querySelector("#containers-section summary"), null);

  teardown(window);
});

test("the tail button starts and stops polling that container's log tail", async () => {
  const window = freshWindow("http://localhost/deployments/example.com/logs");
  setup();
  let tailCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).includes("/tail")) {
      tailCalls++;
      return { ok: true, json: async () => ({ lines: [`tail #${tailCalls}`], error: null }) };
    }
    return {
      ok: true,
      json: async () => ({ status: null, error: null, containers: { "glow-web-1": ["initial"] }, containers_error: null }),
    };
  };

  // Track live intervals directly instead of waiting out the real 5s poll
  // interval to prove "stop" actually clears it.
  const liveIntervals = new Set();
  const realSetInterval = window.setInterval.bind(window);
  const realClearInterval = window.clearInterval.bind(window);
  window.setInterval = (...args) => {
    const id = realSetInterval(...args);
    liveIntervals.add(id);
    return id;
  };
  window.clearInterval = (id) => {
    liveIntervals.delete(id);
    return realClearInterval(id);
  };

  init();
  await wait(window, 50);

  const button = document.querySelector("#containers-section button");
  const pre = document.querySelector("#containers-section pre");
  assert.equal(button.textContent, "Tail");

  button.dispatchEvent(new window.Event("click"));
  await wait(window, 50);
  assert.equal(button.textContent, "Stop tailing");
  assert.equal(pre.innerHTML, "tail #1");
  assert.equal(liveIntervals.size, 1);

  button.dispatchEvent(new window.Event("click"));
  assert.equal(button.textContent, "Tail");
  assert.equal(liveIntervals.size, 0);

  teardown(window);
});

test("a tail response with no lines leaves the previous output in place", async () => {
  const window = freshWindow("http://localhost/deployments/example.com/logs");
  setup();
  let tailCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).includes("/tail")) {
      tailCalls++;
      const lines = tailCalls === 1 ? ["first"] : null;
      return { ok: true, json: async () => ({ lines, error: null }) };
    }
    return {
      ok: true,
      json: async () => ({ status: null, error: null, containers: { "glow-web-1": ["initial"] }, containers_error: null }),
    };
  };

  init();
  await wait(window, 50);

  const button = document.querySelector("#containers-section button");
  const pre = document.querySelector("#containers-section pre");

  button.dispatchEvent(new window.Event("click")); // start: first fetchTail call -> "first"
  await wait(window, 50);
  assert.equal(pre.innerHTML, "first");

  button.dispatchEvent(new window.Event("click")); // stop
  button.dispatchEvent(new window.Event("click")); // start again: second call -> lines: null
  await wait(window, 50);
  assert.equal(pre.innerHTML, "first"); // untouched, not blanked

  teardown(window);
});

test("init does nothing off the /deployments/:domain/logs path", async () => {
  const window = freshWindow("http://localhost/deployments");
  setup();
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return { ok: true, json: async () => ({}) };
  };

  init();
  await wait(window, 50);

  assert.equal(calls, 0);

  teardown(window);
});
