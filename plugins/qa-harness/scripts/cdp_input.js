#!/usr/bin/env node
//
// cdp_input.js -- CDP-based WebView text input
//
// Handles Korean text and React controlled components via
// nativeValueSetter + dispatchEvent pattern.
//
// Key issue references:
//   #1495 -- nativeValueSetter pattern for React controlled inputs
//   #1763 -- focus + setValue in SINGLE evaluate call (race condition fix)
//   #1761 -- reset _valueTracker to prevent React dedup
//
// ENV:
//   SELECTOR  -- CSS selector for the input element
//   VALUE     -- Text to input (supports Korean/CJK)
//   DEVICE    -- ADB device id (optional)
//   PORT      -- CDP port (default 5100)
//
// Exit 0 on success, exit 1 on failure.

"use strict";

const SELECTOR = process.env.SELECTOR;
const VALUE = process.env.VALUE;
const DEVICE = process.env.DEVICE || "";
const PORT = process.env.PORT || "5100";
const TIMEOUT_MS = 15_000;
const POLL_INTERVAL_MS = 500;

if (!SELECTOR) {
  console.error("[cdp_input] ERROR: SELECTOR env var is required");
  process.exit(1);
}
if (VALUE === undefined || VALUE === null) {
  console.error("[cdp_input] ERROR: VALUE env var is required");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// CDP WebSocket helpers
// ---------------------------------------------------------------------------

let WebSocket;
try {
  WebSocket = require("ws");
} catch {
  console.error("[cdp_input] ERROR: 'ws' module not found. Install with: npm i ws");
  process.exit(1);
}

let msgId = 0;

function cdpSend(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const timeout = setTimeout(() => {
      reject(new Error(`CDP command '${method}' timed out after 10s`));
    }, 10_000);

    const handler = (raw) => {
      let msg;
      try { msg = JSON.parse(raw.toString()); } catch { return; }
      if (msg.id === id) {
        ws.removeListener("message", handler);
        clearTimeout(timeout);
        if (msg.error) {
          reject(new Error(`CDP error [${method}]: ${msg.error.message}`));
        } else {
          resolve(msg.result);
        }
      }
    };
    ws.on("message", handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function getDebugUrl() {
  const url = `http://localhost:${PORT}/json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch CDP targets from ${url}: ${res.status}`);
  }
  const targets = await res.json();
  const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
  if (!page) {
    throw new Error("No debuggable page target found on CDP endpoint");
  }
  return page.webSocketDebuggerUrl;
}

function connectWs(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl, { perMessageDeflate: false });
    ws.once("open", () => resolve(ws));
    ws.once("error", reject);
    const timeout = setTimeout(() => {
      reject(new Error("WebSocket connection timed out"));
      ws.close();
    }, 10_000);
    ws.once("open", () => clearTimeout(timeout));
  });
}

async function waitForElement(ws, selector) {
  const deadline = Date.now() + TIMEOUT_MS;

  while (Date.now() < deadline) {
    const result = await cdpSend(ws, "Runtime.evaluate", {
      expression: `!!document.querySelector(${JSON.stringify(selector)})`,
      returnByValue: true,
    });
    if (result.result.value === true) return true;
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  return false;
}

async function setInputValue(ws, selector, value) {
  // Single Runtime.evaluate call combining focus + nativeValueSetter + events
  // to avoid race conditions (issue #1763).
  //
  // Pattern:
  //   1. Find element by selector
  //   2. Focus element
  //   3. Get nativeValueSetter from HTMLInputElement or HTMLTextAreaElement prototype
  //   4. Reset React's _valueTracker to prevent dedup (issue #1761)
  //   5. Call nativeValueSetter with the value
  //   6. Dispatch InputEvent (inputType: 'insertText', data: value)
  //   7. Dispatch Event('change', {bubbles: true})

  const expr = `
    (function() {
      var el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return { ok: false, error: "Element not found" };

      // Step 2: focus
      el.focus();

      // Step 3: get nativeValueSetter from prototype chain
      var proto = Object.getPrototypeOf(el);
      var descriptor =
        Object.getOwnPropertyDescriptor(proto, 'value') ||
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value') ||
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');

      if (!descriptor || !descriptor.set) {
        return { ok: false, error: "Cannot find nativeValueSetter on element prototype" };
      }

      var nativeValueSetter = descriptor.set;

      // Step 4: reset _valueTracker to prevent React dedup (issue #1761)
      var tracker = el._valueTracker;
      if (tracker) {
        tracker.setValue('');
      }

      // Step 5: set value via native setter
      nativeValueSetter.call(el, ${JSON.stringify(value)});

      // Step 6: dispatch InputEvent
      el.dispatchEvent(new InputEvent('input', {
        bubbles: true,
        cancelable: true,
        inputType: 'insertText',
        data: ${JSON.stringify(value)}
      }));

      // Step 7: dispatch change event
      el.dispatchEvent(new Event('change', { bubbles: true }));

      return { ok: true };
    })()
  `;

  const result = await cdpSend(ws, "Runtime.evaluate", {
    expression: expr,
    returnByValue: true,
  });

  if (result.exceptionDetails) {
    throw new Error(
      `Runtime.evaluate exception: ${result.exceptionDetails.text}`
    );
  }

  const val = result.result.value;
  if (!val || !val.ok) {
    throw new Error(`Input failed: ${val ? val.error : "unknown error"}`);
  }
}

async function main() {
  console.log(`[cdp_input] Connecting to CDP on port ${PORT}...`);
  console.log(`[cdp_input] Selector: ${SELECTOR}`);
  console.log(`[cdp_input] Value length: ${VALUE.length} chars`);

  let wsUrl;
  try {
    wsUrl = await getDebugUrl();
  } catch (err) {
    console.error(`[cdp_input] ERROR: Could not get debug URL: ${err.message}`);
    process.exit(1);
  }

  let ws;
  try {
    ws = await connectWs(wsUrl);
  } catch (err) {
    console.error(`[cdp_input] ERROR: WebSocket connect failed: ${err.message}`);
    process.exit(1);
  }

  console.log("[cdp_input] Connected. Waiting for element...");

  const found = await waitForElement(ws, SELECTOR);
  if (!found) {
    console.error(
      `[cdp_input] ERROR: Element '${SELECTOR}' not found within ${TIMEOUT_MS / 1000}s`
    );
    ws.close();
    process.exit(1);
  }

  console.log("[cdp_input] Element found. Setting value...");

  try {
    await setInputValue(ws, SELECTOR, VALUE);
    console.log("[cdp_input] Value set successfully");
  } catch (err) {
    console.error(`[cdp_input] ERROR: ${err.message}`);
    ws.close();
    process.exit(1);
  }

  ws.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(`[cdp_input] FATAL: ${err.message}`);
  process.exit(1);
});
