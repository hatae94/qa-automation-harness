#!/usr/bin/env node
//
// tap_remote.js -- CDP-based WebView element tap
//
// Used by maestro-runner's `runScript` command.
// Connects to Chrome DevTools Protocol via ADB forward port,
// finds element by CSS selector, dispatches isTrusted mouse events.
//
// ENV:
//   SELECTOR  -- CSS selector (e.g. [data-testid="login-btn"])
//   DEVICE    -- ADB device id (optional, used for adb forward)
//   PORT      -- CDP port (default 5100)
//
// Exit 0 on success, exit 1 on failure.

"use strict";

const SELECTOR = process.env.SELECTOR;
const DEVICE = process.env.DEVICE || "";
const PORT = process.env.PORT || "5100";
const TIMEOUT_MS = 15_000;
const POLL_INTERVAL_MS = 500;

if (!SELECTOR) {
  console.error("[tap_remote] ERROR: SELECTOR env var is required");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// CDP WebSocket helpers
// ---------------------------------------------------------------------------

const { WebSocket } = require("ws") ?? await importWs();

async function importWs() {
  // Fallback: try dynamic import for ESM environments
  try {
    return await import("ws");
  } catch {
    console.error("[tap_remote] ERROR: 'ws' module not found. Install with: npm i ws");
    process.exit(1);
  }
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

async function findElementCoords(ws, selector) {
  const expr = `
    (function() {
      const el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return {
        x: Math.round(rect.x + rect.width / 2),
        y: Math.round(rect.y + rect.height / 2),
        width: rect.width,
        height: rect.height
      };
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
  return result.result.value; // null if element not found
}

async function dispatchTap(ws, x, y) {
  // mousePressed generates isTrusted: true events (issue #1477)
  await cdpSend(ws, "Input.dispatchMouseEvent", {
    type: "mousePressed",
    x,
    y,
    button: "left",
    clickCount: 1,
  });
  await cdpSend(ws, "Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x,
    y,
    button: "left",
    clickCount: 1,
  });
}

async function main() {
  console.log(`[tap_remote] Connecting to CDP on port ${PORT}...`);
  console.log(`[tap_remote] Selector: ${SELECTOR}`);

  let wsUrl;
  try {
    wsUrl = await getDebugUrl();
  } catch (err) {
    console.error(`[tap_remote] ERROR: Could not get debug URL: ${err.message}`);
    process.exit(1);
  }

  let ws;
  try {
    ws = await connectWs(wsUrl);
  } catch (err) {
    console.error(`[tap_remote] ERROR: WebSocket connect failed: ${err.message}`);
    process.exit(1);
  }

  console.log("[tap_remote] Connected to CDP. Polling for element...");

  const deadline = Date.now() + TIMEOUT_MS;
  let coords = null;

  while (Date.now() < deadline) {
    try {
      coords = await findElementCoords(ws, SELECTOR);
    } catch (err) {
      console.warn(`[tap_remote] WARN: evaluate error: ${err.message}`);
    }
    if (coords) break;
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }

  if (!coords) {
    console.error(
      `[tap_remote] ERROR: Element '${SELECTOR}' not found within ${TIMEOUT_MS / 1000}s`
    );
    ws.close();
    process.exit(1);
  }

  console.log(
    `[tap_remote] Found element at (${coords.x}, ${coords.y}), size ${coords.width}x${coords.height}`
  );

  try {
    await dispatchTap(ws, coords.x, coords.y);
    console.log("[tap_remote] Tap dispatched successfully");
  } catch (err) {
    console.error(`[tap_remote] ERROR: Tap dispatch failed: ${err.message}`);
    ws.close();
    process.exit(1);
  }

  ws.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(`[tap_remote] FATAL: ${err.message}`);
  process.exit(1);
});
