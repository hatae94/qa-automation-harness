#!/usr/bin/env python3
"""
input_server.py -- Flask-based CDP bridge server

Manages CDP connections and provides HTTP endpoints for tapping
and inputting text into WebView elements via Chrome DevTools Protocol.

Endpoints:
    POST /cdp-tap     -- Tap an element by CSS selector
    POST /cdp-input   -- Input text into an element by CSS selector
    GET  /health      -- Health check

ENV:
    PORT    -- Server port (default 5100)
    DEVICE  -- ADB device id (optional, for port forwarding)

Issue references:
    #1687 -- Port cleanup on startup
"""

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from typing import Optional

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("[input_server] ERROR: Flask not found. Install with: pip install flask", file=sys.stderr)
    sys.exit(1)

try:
    import websocket  # websocket-client
except ImportError:
    print("[input_server] ERROR: websocket-client not found. Install with: pip install websocket-client", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[input_server] ERROR: requests not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_PORT = int(os.environ.get("PORT", "5100"))
DEVICE = os.environ.get("DEVICE", "")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
TIMEOUT_S = 15
POLL_INTERVAL_S = 0.5

logging.basicConfig(
    level=logging.INFO,
    format="[input_server] %(levelname)s %(message)s",
)
log = logging.getLogger("input_server")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Port cleanup (issue #1687)
# ---------------------------------------------------------------------------

def cleanup_port(port: int) -> None:
    """Kill any process occupying the given port on startup."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            if pid.isdigit():
                log.warning("Killing process %s on port %d", pid, port)
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    time.sleep(0.5)
                    # Force kill if still alive
                    os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def is_port_available(port: int) -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# ADB port forward management
# ---------------------------------------------------------------------------

def setup_adb_forward(device: str, local_port: int, remote_port: int) -> bool:
    """Forward local port to device's Chrome DevTools port."""
    cmd = ["adb"]
    if device:
        cmd.extend(["-s", device])
    cmd.extend(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            log.error("ADB forward failed: %s", result.stderr.strip())
            return False
        log.info("ADB forward: localhost:%d -> device:%d", local_port, remote_port)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error("ADB forward error: %s", e)
        return False


def remove_adb_forward(local_port: int) -> None:
    """Remove ADB port forward."""
    cmd = ["adb", "forward", "--remove", f"tcp:{local_port}"]
    try:
        subprocess.run(cmd, capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# CDP communication
# ---------------------------------------------------------------------------

def get_debug_ws_url(cdp_port: int) -> Optional[str]:
    """Get the WebSocket debugger URL from CDP /json endpoint."""
    try:
        resp = requests.get(f"http://localhost:{cdp_port}/json", timeout=5)
        resp.raise_for_status()
        targets = resp.json()
        for target in targets:
            if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                return target["webSocketDebuggerUrl"]
        log.error("No debuggable page target found")
        return None
    except Exception as e:
        log.error("Failed to get debug URL: %s", e)
        return None


def cdp_send(ws_conn, method: str, params: dict = None) -> dict:
    """Send a CDP command and wait for response."""
    msg_id = int(time.time() * 1000) % 1_000_000
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params

    ws_conn.send(json.dumps(payload))

    deadline = time.time() + 10
    while time.time() < deadline:
        raw = ws_conn.recv()
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            if "error" in msg:
                raise RuntimeError(f"CDP error [{method}]: {msg['error'].get('message', 'unknown')}")
            return msg.get("result", {})
    raise TimeoutError(f"CDP command '{method}' timed out")


def cdp_connect(cdp_port: int):
    """Connect to CDP WebSocket."""
    ws_url = get_debug_ws_url(cdp_port)
    if not ws_url:
        return None
    try:
        ws_conn = websocket.create_connection(ws_url, timeout=10)
        return ws_conn
    except Exception as e:
        log.error("WebSocket connection failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# CDP operations
# ---------------------------------------------------------------------------

def cdp_find_and_tap(ws_conn, selector: str) -> dict:
    """Find element by selector and dispatch isTrusted tap events."""
    # Poll for element
    expr = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return null;
        var rect = el.getBoundingClientRect();
        return {{
            x: Math.round(rect.x + rect.width / 2),
            y: Math.round(rect.y + rect.height / 2),
            width: rect.width,
            height: rect.height
        }};
    }})()
    """

    deadline = time.time() + TIMEOUT_S
    coords = None

    while time.time() < deadline:
        result = cdp_send(ws_conn, "Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
        })
        val = result.get("result", {}).get("value")
        if val is not None:
            coords = val
            break
        time.sleep(POLL_INTERVAL_S)

    if coords is None:
        return {"ok": False, "error": f"Element '{selector}' not found within {TIMEOUT_S}s"}

    # Dispatch mouse events for isTrusted tap
    cdp_send(ws_conn, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": coords["x"], "y": coords["y"],
        "button": "left", "clickCount": 1,
    })
    cdp_send(ws_conn, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": coords["x"], "y": coords["y"],
        "button": "left", "clickCount": 1,
    })

    return {"ok": True, "x": coords["x"], "y": coords["y"]}


def cdp_set_input(ws_conn, selector: str, value: str) -> dict:
    """Set input value using nativeValueSetter pattern for React compatibility."""
    expr = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return {{ ok: false, error: "Element not found" }};

        el.focus();

        var proto = Object.getPrototypeOf(el);
        var descriptor =
            Object.getOwnPropertyDescriptor(proto, 'value') ||
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value') ||
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');

        if (!descriptor || !descriptor.set) {{
            return {{ ok: false, error: "Cannot find nativeValueSetter" }};
        }}

        var tracker = el._valueTracker;
        if (tracker) {{ tracker.setValue(''); }}

        descriptor.set.call(el, {json.dumps(value)});

        el.dispatchEvent(new InputEvent('input', {{
            bubbles: true, cancelable: true,
            inputType: 'insertText',
            data: {json.dumps(value)}
        }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));

        return {{ ok: true }};
    }})()
    """

    # Poll for element first
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        check = cdp_send(ws_conn, "Runtime.evaluate", {
            "expression": f"!!document.querySelector({json.dumps(selector)})",
            "returnByValue": True,
        })
        if check.get("result", {}).get("value") is True:
            break
        time.sleep(POLL_INTERVAL_S)
    else:
        return {"ok": False, "error": f"Element '{selector}' not found within {TIMEOUT_S}s"}

    result = cdp_send(ws_conn, "Runtime.evaluate", {
        "expression": expr,
        "returnByValue": True,
    })

    if result.get("exceptionDetails"):
        return {"ok": False, "error": result["exceptionDetails"].get("text", "unknown")}

    return result.get("result", {}).get("value", {"ok": False, "error": "No result"})


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "port": SERVER_PORT,
        "cdp_port": CDP_PORT,
        "device": DEVICE or None,
    })


@app.route("/cdp-tap", methods=["POST"])
def cdp_tap():
    """Tap an element by CSS selector via CDP.

    Body JSON:
        selector (str): CSS selector
        device (str, optional): ADB device id
        port (int, optional): CDP port override
    """
    data = request.get_json(force=True, silent=True) or {}
    selector = data.get("selector")
    if not selector:
        return jsonify({"ok": False, "error": "selector is required"}), 400

    cdp_port = data.get("port", CDP_PORT)
    device = data.get("device", DEVICE)

    ws_conn = cdp_connect(cdp_port)
    if not ws_conn:
        return jsonify({"ok": False, "error": "Cannot connect to CDP"}), 502

    try:
        result = cdp_find_and_tap(ws_conn, selector)
        status_code = 200 if result.get("ok") else 404
        return jsonify(result), status_code
    except Exception as e:
        log.error("cdp-tap error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        ws_conn.close()


@app.route("/cdp-input", methods=["POST"])
def cdp_input():
    """Input text into an element by CSS selector via CDP.

    Body JSON:
        selector (str): CSS selector
        value (str): Text to input
        device (str, optional): ADB device id
        port (int, optional): CDP port override
    """
    data = request.get_json(force=True, silent=True) or {}
    selector = data.get("selector")
    value = data.get("value")

    if not selector:
        return jsonify({"ok": False, "error": "selector is required"}), 400
    if value is None:
        return jsonify({"ok": False, "error": "value is required"}), 400

    cdp_port = data.get("port", CDP_PORT)

    ws_conn = cdp_connect(cdp_port)
    if not ws_conn:
        return jsonify({"ok": False, "error": "Cannot connect to CDP"}), 502

    try:
        result = cdp_set_input(ws_conn, selector, value)
        status_code = 200 if result.get("ok") else 400
        return jsonify(result), status_code
    except Exception as e:
        log.error("cdp-input error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        ws_conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Port cleanup on startup (issue #1687)
    if not is_port_available(SERVER_PORT):
        log.warning("Port %d is in use, attempting cleanup...", SERVER_PORT)
        cleanup_port(SERVER_PORT)
        time.sleep(1)
        if not is_port_available(SERVER_PORT):
            log.error("Port %d still in use after cleanup. Aborting.", SERVER_PORT)
            sys.exit(1)

    # Set up ADB forward if device is specified
    if DEVICE:
        if not setup_adb_forward(DEVICE, CDP_PORT, 9222):
            log.warning("ADB forward setup failed; CDP may not be available")

    log.info("Starting CDP bridge server on port %d", SERVER_PORT)
    log.info("CDP target port: %d", CDP_PORT)
    if DEVICE:
        log.info("Device: %s", DEVICE)

    # Register cleanup handler
    def shutdown_handler(signum, frame):
        log.info("Shutting down...")
        if DEVICE:
            remove_adb_forward(CDP_PORT)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    app.run(host="127.0.0.1", port=SERVER_PORT, debug=False)


if __name__ == "__main__":
    main()
