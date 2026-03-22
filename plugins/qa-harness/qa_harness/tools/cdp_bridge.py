"""CDP Bridge Manager -- Manage Chrome DevTools Protocol bridge lifecycle.

Fixes applied:
  C6 -- PID is persisted to /tmp/qa-harness-cdp.pid
"""

from __future__ import annotations

import logging
import os
import signal
from pathlib import Path

import click

from qa_harness.types import CDPBridgeConfig, CDPBridgeStatus

logger = logging.getLogger(__name__)

PID_FILE = Path("/tmp/qa-harness-cdp.pid")


# ---------------------------------------------------------------------------
# PID file helpers (C6 fix)
# ---------------------------------------------------------------------------

def _write_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid), encoding="utf-8")
    logger.info("[cdp-bridge] PID %d written to %s", pid, PID_FILE)


def _read_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        # Verify process is alive
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None


def _clear_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CDP Bridge Manager
# ---------------------------------------------------------------------------

class CDPBridgeManager:
    """Manages input_server.py + ADB forwarding lifecycle."""

    def __init__(self, config: CDPBridgeConfig | None = None):
        self.config = config or CDPBridgeConfig()
        self._started_at: float | None = None
        self._connected_devices: list[str] = []

    # -- lifecycle --

    async def start(self, device_id: str) -> bool:
        """Start the CDP bridge (input_server.py + ADB forwarding)."""
        logger.info("[cdp-bridge] Starting CDP bridge for device: %s", device_id)

        # Clean stale ports
        await self.clean_ports()

        # ADB forward
        if not await self._setup_adb_forward(device_id):
            logger.error("[cdp-bridge] Failed to set up ADB port forwarding")
            return False

        # Start input_server.py
        pid = await self._start_input_server()
        if pid is None:
            logger.error("[cdp-bridge] Failed to start input_server.py")
            return False

        # C6 fix: persist PID
        _write_pid(pid)

        # Wait for health
        if not await self._wait_for_healthy():
            logger.error("[cdp-bridge] Health check failed after startup")
            await self.stop()
            return False

        import time
        self._started_at = time.time()
        self._connected_devices.append(device_id)
        logger.info("[cdp-bridge] CDP bridge started successfully")
        return True

    async def stop(self) -> None:
        """Stop the CDP bridge and clean up."""
        logger.info("[cdp-bridge] Stopping CDP bridge...")

        pid = _read_pid()
        if pid:
            self._kill_process(pid)
        _clear_pid()

        await self.clean_ports()
        self._connected_devices.clear()
        self._started_at = None
        logger.info("[cdp-bridge] CDP bridge stopped")

    def get_status(self) -> CDPBridgeStatus:
        """Return current bridge status, using persisted PID (C6 fix)."""
        pid = _read_pid()
        import time
        uptime = (
            int(time.time() - self._started_at)
            if self._started_at
            else None
        )
        return CDPBridgeStatus(
            running=pid is not None,
            pid=pid,
            port=self.config.port,
            connected_devices=list(self._connected_devices),
            uptime=uptime,
        )

    async def restart(self, device_id: str) -> bool:
        await self.stop()
        import asyncio
        await asyncio.sleep(1)
        return await self.start(device_id)

    # -- ADB --

    async def _setup_adb_forward(self, device_id: str) -> bool:
        port = self.config.adb_forward_port
        logger.info("[cdp-bridge] ADB forward: tcp:%d -> chrome_devtools_remote", port)
        # Production: subprocess call to adb -s <device> forward ...
        logger.info("[cdp-bridge] [SIMULATED] adb -s %s forward tcp:%d localabstract:chrome_devtools_remote", device_id, port)
        return True

    async def clean_ports(self) -> None:
        logger.info("[cdp-bridge] Cleaning ADB forward ports...")
        logger.info("[cdp-bridge] [SIMULATED] adb forward --remove-all")

    # -- input_server.py --

    async def _start_input_server(self) -> int | None:
        port = self.config.port
        path = self.config.input_server_path
        logger.info("[cdp-bridge] Starting input_server.py on port %d", port)
        # Production: subprocess.Popen(...)
        logger.info("[cdp-bridge] [SIMULATED] python3 %s --port %d &", path, port)
        return 99999  # simulated PID

    @staticmethod
    def _kill_process(pid: int) -> None:
        logger.info("[cdp-bridge] Killing process %d", pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    # -- health --

    async def health_check(self) -> bool:
        """Check if input_server.py is responding."""
        pid = _read_pid()
        if pid is None:
            return False
        url = f"http://{self.config.host}:{self.config.port}/health"
        logger.info("[cdp-bridge] Health check: GET %s", url)
        # Production: httpx.get(url)
        return True

    async def _wait_for_healthy(self) -> bool:
        import asyncio, time
        timeout = self.config.connection_timeout_ms / 1000
        start = time.time()
        delay = 0.5
        while time.time() - start < timeout:
            if await self.health_check():
                return True
            logger.info("[cdp-bridge] Waiting... (retry in %.1fs)", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 5.0)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group("cdp")
def cdp_group() -> None:
    """Manage the CDP bridge lifecycle."""


@cdp_group.command("start")
@click.option("--device", default="emulator-5554")
@click.option("--port", default=5100, type=int)
def cdp_start(device: str, port: int) -> None:
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mgr = CDPBridgeManager(CDPBridgeConfig(port=port))
    asyncio.run(mgr.start(device))


@cdp_group.command("stop")
def cdp_stop() -> None:
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mgr = CDPBridgeManager()
    asyncio.run(mgr.stop())


@cdp_group.command("status")
def cdp_status() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mgr = CDPBridgeManager()
    status = mgr.get_status()
    click.echo(status.model_dump_json(indent=2))


@cdp_group.command("health")
def cdp_health() -> None:
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mgr = CDPBridgeManager()
    ok = asyncio.run(mgr.health_check())
    click.echo(f"Health: {'OK' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit(1)


@cdp_group.command("clean")
def cdp_clean() -> None:
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mgr = CDPBridgeManager()
    asyncio.run(mgr.clean_ports())
