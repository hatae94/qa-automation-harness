#!/usr/bin/env node
//
// check_renderer.js -- Detect if current screen is WebView or Native
//
// Used by maestro-runner to determine the appropriate interaction method
// (CDP for WebView, ADB for native).
//
// ENV:
//   EXPECTED  -- Expected renderer type: "webview" or "native"
//   DEVICE    -- ADB device id (optional)
//   PORT      -- CDP port for WebView detection (default 5100)
//
// Exit 0 if actual renderer matches EXPECTED (or if EXPECTED is not set,
//         prints the detected type).
// Exit 1 if mismatch or detection fails.

"use strict";

const EXPECTED = (process.env.EXPECTED || "").toLowerCase();
const DEVICE = process.env.DEVICE || "";
const PORT = process.env.PORT || "5100";

// ---------------------------------------------------------------------------
// Detection strategies
// ---------------------------------------------------------------------------

/**
 * Strategy 1: Try connecting to CDP /json endpoint.
 * If a debuggable page exists, we're in a WebView.
 */
async function checkCdpAvailable() {
  try {
    const url = `http://localhost:${PORT}/json`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);

    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);

    if (!res.ok) return false;

    const targets = await res.json();
    const hasPage = targets.some(
      (t) => t.type === "page" && t.webSocketDebuggerUrl
    );
    return hasPage;
  } catch {
    return false;
  }
}

/**
 * Strategy 2: Use ADB dumpsys to check for active WebView.
 * Look for WebView-related windows in the window manager.
 */
async function checkAdbWebView() {
  const { execSync } = require("child_process");

  const adbCmd = DEVICE ? `adb -s ${DEVICE}` : "adb";

  try {
    // Check for WebView in the current activity's view hierarchy
    const dumpsys = execSync(
      `${adbCmd} shell dumpsys activity top 2>/dev/null | grep -i webview | head -5`,
      { timeout: 5000, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }
    );
    return dumpsys.trim().length > 0;
  } catch {
    return false;
  }
}

/**
 * Strategy 3: Check if the focused window is a WebView via dumpsys window.
 */
async function checkWindowManager() {
  const { execSync } = require("child_process");

  const adbCmd = DEVICE ? `adb -s ${DEVICE}` : "adb";

  try {
    const windows = execSync(
      `${adbCmd} shell dumpsys window windows 2>/dev/null | grep -E "mCurrentFocus|mFocusedWindow" | head -3`,
      { timeout: 5000, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }
    );
    // WebView windows typically have identifiable patterns
    const lc = windows.toLowerCase();
    return lc.includes("webview") || lc.includes("chromium") || lc.includes("browser");
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function detectRenderer() {
  // Run CDP check and ADB checks in parallel for speed
  const [cdpAvailable, adbWebView, windowHasWebView] = await Promise.all([
    checkCdpAvailable(),
    checkAdbWebView(),
    checkWindowManager(),
  ]);

  // CDP availability is the strongest signal
  if (cdpAvailable) return "webview";
  // ADB-based checks as fallback
  if (adbWebView || windowHasWebView) return "webview";

  return "native";
}

async function main() {
  const detected = await detectRenderer();

  console.log(`[check_renderer] Detected: ${detected}`);

  if (!EXPECTED) {
    // No assertion mode -- just print the detected type
    console.log(detected);
    process.exit(0);
  }

  if (EXPECTED !== "webview" && EXPECTED !== "native") {
    console.error(
      `[check_renderer] ERROR: EXPECTED must be "webview" or "native", got "${EXPECTED}"`
    );
    process.exit(1);
  }

  if (detected === EXPECTED) {
    console.log(`[check_renderer] OK: screen is ${detected} (matches expected)`);
    process.exit(0);
  } else {
    console.error(
      `[check_renderer] MISMATCH: expected=${EXPECTED}, detected=${detected}`
    );
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(`[check_renderer] FATAL: ${err.message}`);
  process.exit(1);
});
