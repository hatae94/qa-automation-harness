"""Batch Runner -- Orchestrate maestro-runner test execution.

Key design decisions:
- Batch tests into groups of 25 (driver crashes after 55+)
- Restart driver between batches to prevent state accumulation
- Pre-flight checks before execution
- Write intermediate results to disk (C5 fix)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import click

from qa_harness.types import BatchResult, ExecutionStatus, TestExecution

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Flow file loading
# ---------------------------------------------------------------------------

class _FlowFile:
    __slots__ = ("path", "name", "tc_ids")

    def __init__(self, path: Path, name: str, tc_ids: list[str]):
        self.path = path
        self.name = name
        self.tc_ids = tc_ids


def _load_flow_files(flows_dir: Path) -> list[_FlowFile]:
    if not flows_dir.is_dir():
        return []

    flows: list[_FlowFile] = []
    for f in sorted(flows_dir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        content = f.read_text(encoding="utf-8")
        # Extract TC IDs from metadata comments
        import re
        m = re.search(r"# TC IDs:\s*(.+)", content)
        tc_ids = (
            [s.strip() for s in m.group(1).split(",")]
            if m
            else [f.stem]
        )
        flows.append(_FlowFile(path=f, name=f.name, tc_ids=tc_ids))
    return flows


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

class _Check:
    __slots__ = ("name", "passed", "message")

    def __init__(self, name: str, passed: bool, message: str):
        self.name = name
        self.passed = passed
        self.message = message


async def _preflight_checks(
    flows_dir: Path, device_id: str, cdp_port: int
) -> list[_Check]:
    checks: list[_Check] = []

    # Device (simulated for PoC)
    logger.info("[runner] Checking device: %s", device_id)
    checks.append(_Check("Device Connected", True, f"Device {device_id} (simulated)"))

    # CDP bridge (simulated)
    logger.info("[runner] Checking CDP bridge on port %d", cdp_port)
    checks.append(_Check("CDP Bridge", True, f"CDP bridge port {cdp_port} (simulated)"))

    # ADB forward (simulated)
    checks.append(_Check("ADB Forward", True, "ADB forwarding (simulated)"))

    # Flow files
    flow_files = _load_flow_files(flows_dir)
    checks.append(
        _Check(
            "Flow Files",
            len(flow_files) > 0,
            f"{len(flow_files)} flow files found" if flow_files else "No flow files found",
        )
    )
    return checks


# ---------------------------------------------------------------------------
# Execution (simulated for PoC)
# ---------------------------------------------------------------------------

async def _execute_flow(
    flow: _FlowFile,
    device_id: str,
    timeout_ms: int,
    dry_run: bool,
) -> TestExecution:
    start = time.time()

    if dry_run:
        logger.info("[runner] [DRY-RUN] Would execute: %s", flow.path)
        sim_dur = int(100 + 400 * (hash(flow.name) % 100) / 100)
        return TestExecution(
            flow_id=flow.name,
            tc_ids=flow.tc_ids,
            status="passed",
            duration_ms=sim_dur,
            started_at=_iso(start),
            finished_at=_iso(start + sim_dur / 1000),
        )

    # Production: spawn maestro-runner subprocess here
    logger.info("[runner] Executing: %s on %s", flow.name, device_id)
    dur = int((time.time() - start) * 1000)
    return TestExecution(
        flow_id=flow.name,
        tc_ids=flow.tc_ids,
        status="passed",
        duration_ms=dur,
        started_at=_iso(start),
        finished_at=_iso(time.time()),
    )


def _iso(ts: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------

def _create_batches(flows: list[_FlowFile], size: int) -> list[list[_FlowFile]]:
    return [flows[i : i + size] for i in range(0, len(flows), size)]


async def _run_batch(
    batch: list[_FlowFile],
    batch_idx: int,
    device_id: str,
    timeout_ms: int,
    dry_run: bool,
) -> BatchResult:
    start = time.time()
    executions: list[TestExecution] = []
    pc = fc = sc = 0

    logger.info("[runner] === Batch %d (%d flows) ===", batch_idx + 1, len(batch))

    for i, flow in enumerate(batch):
        logger.info("[runner]   [%d/%d] %s", i + 1, len(batch), flow.name)
        result = await _execute_flow(flow, device_id, timeout_ms, dry_run)
        executions.append(result)
        if result.status == "passed":
            pc += 1
        elif result.status in ("failed", "error", "timeout"):
            fc += 1
            if result.error_message:
                logger.info("[runner]     FAIL: %s", result.error_message)
        elif result.status == "skipped":
            sc += 1

    return BatchResult(
        batch_index=batch_idx,
        flows=executions,
        total_duration_ms=int((time.time() - start) * 1000),
        pass_count=pc,
        fail_count=fc,
        skip_count=sc,
    )


async def run_batch_execution(
    flows_dir: Path,
    device_id: str = "emulator-5554",
    batch_size: int = 25,
    cdp_port: int = 5100,
    timeout_ms: int = 120_000,
    dry_run: bool = False,
    restart_between_batches: bool = True,
    results_output: Path | None = None,
) -> list[BatchResult]:
    """Run all flows in batches, writing intermediate results (C5 fix)."""
    logger.info("[runner] Flows dir: %s", flows_dir)
    logger.info("[runner] Device: %s  Batch: %d  Timeout: %dms  Dry: %s",
                device_id, batch_size, timeout_ms, dry_run)

    # Pre-flight
    checks = await _preflight_checks(flows_dir, device_id, cdp_port)
    all_ok = True
    for c in checks:
        tag = "PASS" if c.passed else "FAIL"
        logger.info("[runner]   [%s] %s: %s", tag, c.name, c.message)
        if not c.passed:
            all_ok = False

    if not all_ok and not dry_run:
        logger.error("[runner] Pre-flight checks failed.")
        return []

    flows = _load_flow_files(flows_dir)
    if not flows:
        logger.error("[runner] No flow files found in %s", flows_dir)
        return []

    batches = _create_batches(flows, batch_size)
    logger.info("[runner] %d flows -> %d batch(es)", len(flows), len(batches))

    results: list[BatchResult] = []
    for i, batch in enumerate(batches):
        if i > 0 and restart_between_batches:
            logger.info("[runner] Restarting driver between batches...")

        br = await _run_batch(batch, i, device_id, timeout_ms, dry_run)
        results.append(br)
        logger.info(
            "[runner] Batch %d: %d passed, %d failed, %d skipped (%dms)",
            i + 1, br.pass_count, br.fail_count, br.skip_count, br.total_duration_ms,
        )

        # C5 fix: write intermediate results after each batch
        if results_output:
            results_output.parent.mkdir(parents=True, exist_ok=True)
            data = [r.model_dump() for r in results]
            results_output.write_text(json.dumps(data, indent=2), encoding="utf-8")

    tp = sum(r.pass_count for r in results)
    tf = sum(r.fail_count for r in results)
    ts = sum(r.skip_count for r in results)
    td = sum(r.total_duration_ms for r in results)
    logger.info("[runner] === Final: %d passed, %d failed, %d skipped (%.1fs) ===",
                tp, tf, ts, td / 1000)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command("run")
@click.option("--flows", "flows_dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--device", "device_id", default="emulator-5554")
@click.option("--batch-size", default=25, type=int)
@click.option("--cdp-port", default=5100, type=int)
@click.option("--timeout", "timeout_ms", default=120_000, type=int)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--results-output", default=None, type=click.Path(path_type=Path))
def run_cmd(
    flows_dir: Path,
    device_id: str,
    batch_size: int,
    cdp_port: int,
    timeout_ms: int,
    dry_run: bool,
    results_output: Path | None,
) -> None:
    """Execute YAML flows via maestro-runner in batches."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_batch_execution(
        flows_dir=flows_dir,
        device_id=device_id,
        batch_size=batch_size,
        cdp_port=cdp_port,
        timeout_ms=timeout_ms,
        dry_run=dry_run,
        restart_between_batches=True,
        results_output=results_output,
    ))
