import "./test-env.js";
import { test } from "node:test";
import assert from "node:assert/strict";
import { freshWindow, teardown } from "./dom-setup.js";
import { init } from "../test-build/sso-copy.js";

function wait(window, ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

test("clicking the button copies the code and flips the label back after a delay", async () => {
  const window = freshWindow();
  document.body.innerHTML = `
    <span id="user-code">ABCD-1234</span>
    <button id="copy-user-code">Copy</button>
  `;
  const copied = [];
  globalThis.navigator.clipboard.writeText = async (text) => {
    copied.push(text);
  };

  init();
  const button = document.getElementById("copy-user-code");
  button.dispatchEvent(new window.Event("click"));
  await null; // let the writeText().then(...) microtask run

  assert.deepEqual(copied, ["ABCD-1234"]);
  assert.equal(button.textContent, "Copied!");

  await wait(window, 1600);
  assert.equal(button.textContent, "Copy");

  teardown(window);
});

test("does nothing when the button or code element is missing", () => {
  const window = freshWindow();
  document.body.innerHTML = "";
  assert.doesNotThrow(() => init());
  teardown(window);
});
