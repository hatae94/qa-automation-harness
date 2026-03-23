"""Main CLI entry point for the QA Automation Harness.

All subcommands are assembled here via click groups.
M8 fix: config is loaded from YAML / CLI flags, not hardcoded.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click

from qa_harness.config import load_config

logger = logging.getLogger(__name__)


@click.group()
@click.option("--config", "config_path", default=None, type=click.Path(path_type=Path),
              help="Path to qa-harness.yaml config file")
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.pass_context
def main(ctx: click.Context, config_path: Path | None, verbose: bool) -> None:
    """QA Automation Harness -- deterministic test generation and execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


# ---------------------------------------------------------------------------
# parse-tc
# ---------------------------------------------------------------------------

@main.command("parse-tc")
@click.option("-i", "--input", "input_path", required=True,
              type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", "output_path", required=True,
              type=click.Path(path_type=Path))
def parse_tc(input_path: Path, output_path: Path) -> None:
    """Parse TC CSV spreadsheet into normalized JSON."""
    from qa_harness.tools.tc_parser import parse_tc_file

    logger.info("[tc-parser] Reading CSV from: %s", input_path)
    result = parse_tc_file(input_path)
    logger.info("[tc-parser] Parsed %d test cases", len(result.test_cases))

    if result.errors:
        logger.warning("[tc-parser] %d parse errors", len(result.errors))
        for e in result.errors:
            logger.warning("  Row %d: %s", e.row, e.message)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    logger.info("[tc-parser] Output written to: %s", output_path)


# ---------------------------------------------------------------------------
# generate-yaml
# ---------------------------------------------------------------------------

@main.command("generate-yaml")
@click.option("--tc", "tc_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--catalog", "catalog_dir", default=None, type=click.Path(path_type=Path))
@click.option("--templates", "templates_dir", default=None, type=click.Path(path_type=Path))
@click.option("--output", "output_dir", default=None, type=click.Path(path_type=Path))
@click.option("--test-accounts", "test_accounts_path", default=None, type=click.Path(path_type=Path))
@click.pass_context
def generate_yaml(
    ctx: click.Context,
    tc_path: Path,
    catalog_dir: Path | None,
    templates_dir: Path | None,
    output_dir: Path | None,
    test_accounts_path: Path | None,
) -> None:
    """Generate maestro-runner YAML flows from parsed TCs."""
    from qa_harness.tools.yaml_generator import generate_yaml_flows

    cfg = load_config(ctx.obj.get("config_path"))
    generate_yaml_flows(
        tc_path=tc_path,
        catalog_dir=Path(catalog_dir or cfg.catalog_dir),
        flow_graph_path=Path(cfg.flow_graph_path),
        templates_dir=Path(templates_dir or cfg.templates_dir),
        output_dir=Path(output_dir or cfg.output_dir),
        test_accounts_path=Path(test_accounts_path or cfg.test_accounts_path),
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@main.command("validate")
@click.option("--flows", "flows_dir", default=None, type=click.Path(path_type=Path))
@click.option("--catalog", "catalog_dir", default=None, type=click.Path(path_type=Path))
@click.pass_context
def validate(ctx: click.Context, flows_dir: Path | None, catalog_dir: Path | None) -> None:
    """Validate generated YAML flows against the catalog."""
    from qa_harness.tools.yaml_validator import validate_flows

    cfg = load_config(ctx.obj.get("config_path"))
    result = validate_flows(
        flows_dir=Path(flows_dir or cfg.output_dir),
        catalog_dir=Path(catalog_dir or cfg.catalog_dir),
        flow_graph_path=Path(cfg.flow_graph_path),
    )
    if not result.valid:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@main.command("run")
@click.option("--flows", "flows_dir", default=None, type=click.Path(path_type=Path))
@click.option("--device", "device_id", default=None)
@click.option("--batch-size", default=None, type=int)
@click.option("--timeout", "timeout_ms", default=None, type=int)
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def run(
    ctx: click.Context,
    flows_dir: Path | None,
    device_id: str | None,
    batch_size: int | None,
    timeout_ms: int | None,
    dry_run: bool,
) -> None:
    """Execute YAML flows via maestro-runner in batches."""
    from qa_harness.tools.batch_runner import run_batch_execution

    cfg = load_config(ctx.obj.get("config_path"))
    asyncio.run(run_batch_execution(
        flows_dir=Path(flows_dir or cfg.output_dir),
        device_id=device_id or cfg.device_id or "emulator-5554",
        batch_size=batch_size or cfg.batch_size,
        cdp_port=cfg.cdp_bridge.port,
        timeout_ms=timeout_ms or cfg.flow_timeout_ms,
        dry_run=dry_run,
        restart_between_batches=cfg.restart_between_batches,
        results_output=Path(cfg.reports_dir) / "batch-results.json",
    ))


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@main.command("report")
@click.option("--results", "results_path", default=None, type=click.Path(path_type=Path))
@click.option("--tc-map", "tc_map_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", "output_dir", default=None, type=click.Path(path_type=Path))
@click.pass_context
def report(
    ctx: click.Context,
    results_path: Path | None,
    tc_map_path: Path,
    output_dir: Path | None,
) -> None:
    """Generate HTML/JSON/Telegram reports from test results."""
    from qa_harness.tools.report_generator import run_report_generator

    cfg = load_config(ctx.obj.get("config_path"))
    run_report_generator(
        results_path=results_path,
        tc_map_path=tc_map_path,
        output_dir=Path(output_dir or cfg.reports_dir),
    )


# ---------------------------------------------------------------------------
# cdp
# ---------------------------------------------------------------------------

@main.group("cdp")
def cdp() -> None:
    """Manage the CDP bridge lifecycle."""


@cdp.command("start")
@click.option("--device", default="emulator-5554")
@click.option("--port", default=5100, type=int)
def cdp_start(device: str, port: int) -> None:
    from qa_harness.tools.cdp_bridge import CDPBridgeManager, CDPBridgeConfig
    mgr = CDPBridgeManager(CDPBridgeConfig(port=port))
    asyncio.run(mgr.start(device))


@cdp.command("stop")
def cdp_stop() -> None:
    from qa_harness.tools.cdp_bridge import CDPBridgeManager
    mgr = CDPBridgeManager()
    asyncio.run(mgr.stop())


@cdp.command("status")
def cdp_status() -> None:
    from qa_harness.tools.cdp_bridge import CDPBridgeManager
    mgr = CDPBridgeManager()
    click.echo(mgr.get_status().model_dump_json(indent=2))


@cdp.command("health")
def cdp_health() -> None:
    from qa_harness.tools.cdp_bridge import CDPBridgeManager
    mgr = CDPBridgeManager()
    ok = asyncio.run(mgr.health_check())
    click.echo(f"Health: {'OK' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

@main.group("index")
def index() -> None:
    """Build and manage the app knowledge base."""


@index.command("build")
@click.option("--device", required=True, help="ADB device ID (e.g., emulator-5554)")
@click.option("--app", required=True, help="App package name (e.g., com.alphaz.app)")
@click.option("--output", "output_dir", default="src/knowledge/screens", type=click.Path(path_type=Path))
def index_build(device: str, app: str, output_dir: Path) -> None:
    """Scan app screens via maestro hierarchy and build knowledge base."""
    import subprocess

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = output_dir.parent / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"[index] Scanning app {app} on device {device}")
    click.echo(f"[index] Output: {output_dir}")

    # Dump hierarchy
    try:
        result = subprocess.run(
            ["maestro", "--device", device, "hierarchy", "--compact"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            snapshot_path = snapshots_dir / "current_screen.json"
            snapshot_path.write_text(result.stdout, encoding="utf-8")
            click.echo(f"[index] Hierarchy saved to {snapshot_path}")
            click.echo(f"[index] Output length: {len(result.stdout)} chars")
        else:
            click.echo(f"[index] maestro hierarchy failed: {result.stderr}", err=True)
            raise SystemExit(1)
    except FileNotFoundError:
        click.echo("[index] ERROR: maestro CLI not found. Install maestro first.", err=True)
        raise SystemExit(1)


@index.command("validate")
@click.option("--dir", "kb_dir", default="src/knowledge/screens", type=click.Path(path_type=Path))
def index_validate(kb_dir: Path) -> None:
    """Validate knowledge base completeness."""
    from qa_harness.knowledge.catalog import load_catalog

    kb_dir = Path(kb_dir)
    fg_path = kb_dir.parent / "flow-graph.json"
    catalog = load_catalog(kb_dir, fg_path)

    n_screens = len(catalog.screens)
    n_elements = len(catalog.elements_by_selector)
    n_trans = len(catalog.flow_graph.transitions) if catalog.flow_graph else 0

    click.echo(f"[index] Screens: {n_screens}")
    click.echo(f"[index] Elements: {n_elements}")
    click.echo(f"[index] Transitions: {n_trans}")

    if n_screens == 0:
        click.echo("[index] WARNING: No screens indexed. Run 'index build' first.", err=True)
    if n_trans == 0:
        click.echo("[index] WARNING: No transitions defined in flow graph.", err=True)


@index.command("detect-renderer")
@click.option("--device", default="emulator-5554")
def index_detect_renderer(device: str) -> None:
    """Detect WebView vs Native renderer for current screen."""
    import subprocess

    try:
        result = subprocess.run(
            ["maestro", "--device", device, "hierarchy", "--compact"],
            capture_output=True, text=True, timeout=30,
        )
        if "src.web-container" in result.stdout:
            click.echo("[index] Current screen: WEBVIEW")
        else:
            click.echo("[index] Current screen: NATIVE")
    except FileNotFoundError:
        click.echo("[index] ERROR: maestro CLI not found.", err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------

@main.group("triage")
def triage() -> None:
    """Analyze test failures."""


@triage.command("analyze")
@click.option("--results", "results_dir", default="results", type=click.Path(path_type=Path))
@click.option("--tc-id", default=None, help="Analyze specific TC only")
def triage_analyze(results_dir: Path, tc_id: str | None) -> None:
    """Classify failures by error pattern (rules-based)."""
    import re
    results_dir = Path(results_dir)

    patterns = {
        "SELECTOR_NOT_FOUND": re.compile(r"Element .* not found"),
        "TIMEOUT": re.compile(r"Timeout .* exceeded|timed out"),
        "CDP_ERROR": re.compile(r"CDP connection|cdp.*refused"),
        "APP_CRASH": re.compile(r"Process crashed|SIGKILL"),
        "ASSERTION_FAIL": re.compile(r"assertVisible .* failed"),
        "DEVICE_LOST": re.compile(r"device not found|offline"),
    }

    # Read failure logs if available
    log_files = list(results_dir.glob("*.log")) + list(results_dir.glob("*.xml"))
    if not log_files:
        click.echo("[triage] No result files found in " + str(results_dir))
        return

    click.echo(f"[triage] Analyzing {len(log_files)} result files")
    for lf in log_files:
        content = lf.read_text(encoding="utf-8", errors="replace")
        classified = False
        for label, pat in patterns.items():
            if pat.search(content):
                click.echo(f"  [{label}] {lf.name}")
                classified = True
                break
        if not classified:
            click.echo(f"  [UNKNOWN] {lf.name}")


@triage.command("summary")
@click.option("--results", "results_dir", default="results", type=click.Path(path_type=Path))
def triage_summary(results_dir: Path) -> None:
    """Show triage summary of latest results."""
    results_dir = Path(results_dir)
    if not results_dir.exists():
        click.echo("[triage] No results directory found.")
        return
    files = list(results_dir.glob("*.xml")) + list(results_dir.glob("*.json"))
    click.echo(f"[triage] {len(files)} result files in {results_dir}")


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

@main.command("dispatch")
@click.option("--catalog", "catalog_dir", default=None, type=click.Path(path_type=Path))
@click.pass_context
def dispatch(ctx: click.Context, catalog_dir: Path | None) -> None:
    """Analyze renderer types for all cataloged screens."""
    from qa_harness.tools.renderer_dispatch import dispatch_all_screens

    cfg = load_config(ctx.obj.get("config_path"))
    results = dispatch_all_screens(Path(catalog_dir or cfg.catalog_dir))
    click.echo("\nScreen Renderer Map:")
    click.echo("-" * 60)
    for r in results:
        tag = "WEB" if r.renderer_type == "webview" else "NAT"
        click.echo(f"  [{tag}] {r.screen_id:<25} {r.renderer_type:<10} ({r.confidence})")
    click.echo("-" * 60)


# ---------------------------------------------------------------------------
# full: complete pipeline  (C5 fix: proper data flow with intermediate files)
# ---------------------------------------------------------------------------

@main.command("full")
@click.option("-i", "--input", "input_path", required=True,
              type=click.Path(exists=True, path_type=Path))
@click.option("--device", "device_id", default="emulator-5554")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def full_pipeline(ctx: click.Context, input_path: Path, device_id: str, dry_run: bool) -> None:
    """Run the complete pipeline: parse -> generate -> validate -> run -> report."""
    from qa_harness.tools.batch_runner import run_batch_execution
    from qa_harness.tools.report_generator import run_report_generator, write_junit_xml
    from qa_harness.tools.tc_parser import parse_tc_file
    from qa_harness.tools.yaml_generator import generate_yaml_flows
    from qa_harness.tools.yaml_validator import validate_flows

    cfg = load_config(ctx.obj.get("config_path"))

    output_dir = Path(cfg.output_dir)
    reports_dir = Path(cfg.reports_dir)
    parsed_path = output_dir / "_parsed-tc.json"
    manifest_path = output_dir / "_manifest.json"

    # Phase 1: Parse
    click.echo("=== Phase 1: Parse TC CSV ===")
    result = parse_tc_file(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text(result.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    click.echo(f"Parsed {len(result.test_cases)} test cases\n")

    # Phase 2: Generate
    click.echo("=== Phase 2: Generate YAML Flows ===")
    flows = generate_yaml_flows(
        tc_path=parsed_path,
        catalog_dir=Path(cfg.catalog_dir),
        flow_graph_path=Path(cfg.flow_graph_path),
        templates_dir=Path(cfg.templates_dir),
        output_dir=output_dir,
        test_accounts_path=Path(cfg.test_accounts_path),
    )
    click.echo(f"Generated {len(flows)} flows\n")

    # Phase 3: Validate
    click.echo("=== Phase 3: Validate Flows ===")
    val = validate_flows(output_dir, Path(cfg.catalog_dir), Path(cfg.flow_graph_path))
    if not val.valid:
        click.echo("Validation failed. Fix issues before running.", err=True)
        raise SystemExit(1)
    click.echo("")

    # Phase 4: Execute
    click.echo("=== Phase 4: Execute Flows ===")
    batch_results_path = reports_dir / "batch-results.json"
    batches = asyncio.run(run_batch_execution(
        flows_dir=output_dir,
        device_id=device_id,
        batch_size=cfg.batch_size,
        cdp_port=cfg.cdp_bridge.port,
        timeout_ms=cfg.flow_timeout_ms,
        dry_run=dry_run,
        restart_between_batches=cfg.restart_between_batches,
        results_output=batch_results_path,
    ))

    # C5 fix: write JUnit XML from batch results
    junit_path = reports_dir / "results.xml"
    write_junit_xml(batches, junit_path)
    click.echo("")

    # Phase 5: Report
    click.echo("=== Phase 5: Generate Report ===")
    run_report_generator(
        results_path=junit_path,
        tc_map_path=manifest_path,
        output_dir=reports_dir,
    )

    click.echo("\n=== Pipeline Complete ===")


if __name__ == "__main__":
    main()
