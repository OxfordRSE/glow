import "./test-env.js";
import { test } from "node:test";
import assert from "node:assert/strict";
import { freshWindow, teardown } from "./dom-setup.js";
import { init } from "../test-build/heartbeat.js";

test("init pings /heartbeat immediately with POST + keepalive", async () => {
  const window = freshWindow();
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push([url, opts]);
    return { ok: true };
  };

  init();
  await null; // let the fire-and-forget ping() promise settle

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/heartbeat");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].keepalive, true);

  teardown(window);
});

test("init swallows a rejected fetch instead of throwing", async () => {
  const window = freshWindow();
  globalThis.fetch = async () => {
    throw new Error("network down");
  };

  assert.doesNotThrow(() => init());
  await null;

  teardown(window);
});
