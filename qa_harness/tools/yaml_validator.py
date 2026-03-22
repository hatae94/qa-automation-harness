"""YAML Validator -- Validate generated YAML flows before execution.

Catches issues that would cause runtime failures:
1. Unknown selectors not in the catalog
2. Invalid screen transitions not in the flow graph
3. Korean input method mismatch (CDP for WebView, ADB for Native)
4. Unknown maestro-runner commands
5. Unfilled template slots (leftover {{...}} placeholders)
6. Missing required environment variables in runScript steps

Fix M7: warn on empty flows (files with zero steps).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import click
import yaml

from qa_harness.knowledge.catalog import (
    ScreenCatalog,
    load_catalog,
    lookup_element_by_selector,
)
from qa_harness.types import ValidationIssue, ValidationResult, ValidationStats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known maestro-runner commands
# ---------------------------------------------------------------------------

KNOWN_COMMANDS: frozenset[str] = frozenset({
    "launchApp", "stopApp", "clearState",
    "tapOn", "longPressOn", "doubleTapOn",
    "inputText", "eraseText",
    "swipe", "scroll", "scrollUntilVisible",
    "assertVisible", "assertNotVisible",
    "waitForAnimationToEnd", "extendedWaitUntil",
    "runScript", "runFlow",
    "pressKey", "back", "hideKeyboard",
    "takeScreenshot", "setLocation",
    "repeat", "evalScript",
    "copyTextFrom", "pasteText", "openLink",
    "assertTrue",
})

_SLOT_RE = re.compile(r"\{\{(\w+)\}\}")
_KOREAN_RE = re.compile(r"[\u3131-\uD79D]")


# ---------------------------------------------------------------------------
# Parsed flow document
# ---------------------------------------------------------------------------

class _FlowDoc:
    __slots__ = ("file_path", "file_name", "raw", "steps", "metadata")

    def __init__(
        self,
        file_path: Path,
        raw: str,
        steps: list[Any],
        metadata: dict[str, str],
    ):
        self.file_path = file_path
        self.file_name = file_path.name
        self.raw = raw
        self.steps = steps
        self.metadata = metadata


def _parse_flow_file(path: Path) -> _FlowDoc | None:
    """Parse a flow YAML.  C3 fix: errors are propagated, not swallowed."""
    content = path.read_text(encoding="utf-8")

    # Extract metadata from header comments
    metadata: dict[str, str] = {}
    for line in content.splitlines():
        m = re.match(r"^#\s*(.+?):\s*(.+)$", line)
        if m:
            metadata[m.group(1).strip()] = m.group(2).strip()

    parts = content.split("---")
    steps: list[Any] = []
    if len(parts) > 1:
        try:
            parsed = yaml.safe_load(parts[-1])
            if isinstance(parsed, list):
                steps = parsed
        except yaml.YAMLError as exc:
            # C3 fix: surface YAML parse errors
            logger.error("YAML parse error in %s: %s", path.name, exc)
            return None

    return _FlowDoc(file_path=path, raw=content, steps=steps, metadata=metadata)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_unfilled_slots(doc: _FlowDoc) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for m in _SLOT_RE.finditer(doc.raw):
        issues.append(ValidationIssue(
            severity="error",
            code="UNFILLED_SLOT",
            message=f"Unfilled template slot: {{{{{m.group(1)}}}}}",
            file=doc.file_name,
        ))
    return issues


def _check_commands(doc: _FlowDoc) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for i, step in enumerate(doc.steps):
        if not isinstance(step, dict):
            issues.append(ValidationIssue(
                severity="error", code="INVALID_STEP",
                message=f"Step {i} is not a valid object",
                file=doc.file_name, step=i,
            ))
            continue
        for cmd in step:
            if cmd not in KNOWN_COMMANDS:
                issues.append(ValidationIssue(
                    severity="error", code="UNKNOWN_COMMAND",
                    message=f'Unknown command: "{cmd}"',
                    file=doc.file_name, step=i,
                    details={"command": cmd},
                ))
    return issues


def _check_selectors(doc: _FlowDoc, catalog: ScreenCatalog) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for i, step in enumerate(doc.steps):
        if not isinstance(step, dict):
            continue
        for cmd, args in step.items():
            if not isinstance(args, dict):
                continue

            # id-based selector
            sel = args.get("id")
            if isinstance(sel, str) and not lookup_element_by_selector(catalog, sel):
                issues.append(ValidationIssue(
                    severity="warning", code="UNKNOWN_SELECTOR",
                    message=f'Selector "{sel}" not found in catalog',
                    file=doc.file_name, step=i,
                    details={"command": cmd, "selector": sel},
                ))

            # extendedWaitUntil nested selectors
            if cmd == "extendedWaitUntil":
                for key in ("visible", "notVisible"):
                    nested = args.get(key)
                    if isinstance(nested, dict):
                        nid = nested.get("id")
                        if isinstance(nid, str) and not lookup_element_by_selector(catalog, nid):
                            issues.append(ValidationIssue(
                                severity="warning", code="UNKNOWN_SELECTOR",
                                message=f'Wait selector "{nid}" not found in catalog',
                                file=doc.file_name, step=i,
                                details={"command": cmd, "selector": nid},
                            ))

            # runScript env SELECTOR (CDP)
            if cmd == "runScript":
                env = args.get("env")
                if isinstance(env, dict) and "SELECTOR" in env:
                    m = re.search(r"data-testid='([^']+)'", env["SELECTOR"])
                    if m:
                        tid = m.group(1)
                        if not lookup_element_by_selector(catalog, tid):
                            issues.append(ValidationIssue(
                                severity="warning", code="UNKNOWN_CDP_SELECTOR",
                                message=f'CDP selector for testID "{tid}" not found',
                                file=doc.file_name, step=i,
                                details={"command": cmd, "cdpSelector": env["SELECTOR"]},
                            ))
    return issues


def _check_korean_input(doc: _FlowDoc, catalog: ScreenCatalog) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for i, step in enumerate(doc.steps):
        if not isinstance(step, dict):
            continue

        # runScript method mismatch
        if "runScript" in step:
            args = step["runScript"]
            if not isinstance(args, dict):
                continue
            file = args.get("file", "")
            env = args.get("env", {})
            if not isinstance(env, dict):
                continue
            selector = env.get("SELECTOR", "")
            is_webview_input = "cdp_input" in file
            is_native_input = "adb_korean_input" in file
            m = re.search(r"data-testid='([^']+)'", selector)
            if m:
                tid = m.group(1)
                el = lookup_element_by_selector(catalog, tid)
                if el:
                    if el.renderer_type == "native" and is_webview_input:
                        issues.append(ValidationIssue(
                            severity="error", code="KOREAN_INPUT_MISMATCH",
                            message=f'CDP input used for native element "{tid}". Use ADB clipboard.',
                            file=doc.file_name, step=i,
                        ))
                    if el.renderer_type == "webview" and is_native_input:
                        issues.append(ValidationIssue(
                            severity="error", code="KOREAN_INPUT_MISMATCH",
                            message=f'ADB clipboard used for WebView element "{tid}". Use CDP.',
                            file=doc.file_name, step=i,
                        ))

        # Direct Korean inputText
        if "inputText" in step:
            args = step["inputText"]
            text = args.get("text", args) if isinstance(args, dict) else args
            if isinstance(text, str) and _KOREAN_RE.search(text):
                issues.append(ValidationIssue(
                    severity="warning", code="KOREAN_DIRECT_INPUT",
                    message=f'Direct inputText with Korean "{text[:20]}...". Use workaround.',
                    file=doc.file_name, step=i,
                ))
    return issues


def _check_runscript_env(doc: _FlowDoc) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for i, step in enumerate(doc.steps):
        if not isinstance(step, dict) or "runScript" not in step:
            continue
        args = step["runScript"]
        if not isinstance(args, dict):
            continue
        file = args.get("file")
        env = args.get("env", {})
        if not isinstance(env, dict):
            env = {}

        if not file:
            issues.append(ValidationIssue(
                severity="error", code="MISSING_SCRIPT_FILE",
                message='runScript step missing "file" field',
                file=doc.file_name, step=i,
            ))
            continue

        if "tap_remote" in file or "cdp_input" in file:
            if "DEVICE" not in env:
                issues.append(ValidationIssue(
                    severity="error", code="MISSING_ENV_DEVICE",
                    message=f'CDP script "{file}" missing DEVICE env var',
                    file=doc.file_name, step=i,
                ))
            if "PORT" not in env:
                issues.append(ValidationIssue(
                    severity="warning", code="MISSING_ENV_PORT",
                    message=f'CDP script "{file}" missing PORT env var',
                    file=doc.file_name, step=i,
                ))

        if "tap_remote" in file and "SELECTOR" not in env:
            issues.append(ValidationIssue(
                severity="error", code="MISSING_ENV_SELECTOR",
                message="tap_remote.js missing SELECTOR env var",
                file=doc.file_name, step=i,
            ))

        if "cdp_input" in file:
            if "SELECTOR" not in env:
                issues.append(ValidationIssue(
                    severity="error", code="MISSING_ENV_SELECTOR",
                    message="cdp_input.js missing SELECTOR env var",
                    file=doc.file_name, step=i,
                ))
            if "VALUE" not in env and "TEXT" not in env:
                issues.append(ValidationIssue(
                    severity="error", code="MISSING_ENV_VALUE",
                    message="cdp_input.js missing VALUE or TEXT env var",
                    file=doc.file_name, step=i,
                ))
    return issues


def _check_empty_flow(doc: _FlowDoc) -> list[ValidationIssue]:
    """M7 fix: warn when a flow file has zero steps."""
    if not doc.steps:
        return [ValidationIssue(
            severity="warning",
            code="EMPTY_FLOW",
            message="Flow file has no steps",
            file=doc.file_name,
        )]
    return []


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def validate_flows(
    flows_dir: Path,
    catalog_dir: Path,
    flow_graph_path: Path,
) -> ValidationResult:
    """Validate all YAML flow files in *flows_dir*."""
    all_issues: list[ValidationIssue] = []

    logger.info("[validator] Loading screen catalog...")
    catalog = load_catalog(catalog_dir, flow_graph_path)

    yaml_files = sorted(
        f for f in flows_dir.iterdir()
        if f.suffix == ".yaml" and not f.name.startswith("_")
    )
    logger.info("[validator] Found %d flow files to validate", len(yaml_files))

    valid_flows = 0
    invalid_flows = 0
    total_steps = 0

    for yf in yaml_files:
        doc = _parse_flow_file(yf)
        if doc is None:
            all_issues.append(ValidationIssue(
                severity="error", code="INVALID_YAML",
                message=f"Failed to parse YAML file: {yf.name}",
                file=yf.name,
            ))
            invalid_flows += 1
            continue

        total_steps += len(doc.steps)

        file_issues = [
            *_check_unfilled_slots(doc),
            *_check_commands(doc),
            *_check_selectors(doc, catalog),
            *_check_korean_input(doc, catalog),
            *_check_runscript_env(doc),
            *_check_empty_flow(doc),
        ]

        if any(i.severity == "error" for i in file_issues):
            invalid_flows += 1
        else:
            valid_flows += 1

        all_issues.extend(file_issues)

    n_errors = sum(1 for i in all_issues if i.severity == "error")
    n_warnings = sum(1 for i in all_issues if i.severity == "warning")

    result = ValidationResult(
        valid=invalid_flows == 0,
        issues=all_issues,
        stats=ValidationStats(
            total_flows=len(yaml_files),
            valid_flows=valid_flows,
            invalid_flows=invalid_flows,
            total_steps=total_steps,
            warnings=n_warnings,
            errors=n_errors,
        ),
    )

    logger.info("[validator] Total flows: %d", result.stats.total_flows)
    logger.info("[validator] Valid: %d  Invalid: %d", valid_flows, invalid_flows)
    logger.info("[validator] Errors: %d  Warnings: %d", n_errors, n_warnings)

    for issue in all_issues:
        prefix = {"error": "ERR", "warning": "WRN", "info": "INF"}.get(issue.severity, "???")
        loc = f" step {issue.step}" if issue.step is not None else ""
        logger.info("  [%s] %s%s: %s", prefix, issue.file, loc, issue.message)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _discover_flow_graph(catalog_dir: Path) -> Path | None:
    """Auto-discover flow-graph.json near the catalog directory.

    Search order:
      1. <catalog>/../flow-graph.json
      2. <catalog>/../../flow-graph.json
      3. <catalog>/../flows/flow-graph.json
    """
    candidates = [
        catalog_dir.parent / "flow-graph.json",
        catalog_dir.parent.parent / "flow-graph.json",
        catalog_dir.parent / "flows" / "flow-graph.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            logger.info("[validator] Auto-discovered flow graph: %s", candidate)
            return candidate
    return None


@click.command("validate")
@click.option("--flows", "flows_dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--catalog", "catalog_dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--flow-graph", "flow_graph_path", default=None, type=click.Path(path_type=Path))
def validate_cmd(flows_dir: Path, catalog_dir: Path, flow_graph_path: Path | None) -> None:
    """Validate generated YAML flows against the catalog."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if flow_graph_path is None:
        flow_graph_path = _discover_flow_graph(catalog_dir)
    if flow_graph_path is None:
        flow_graph_path = catalog_dir.parent / "flow-graph.json"
    result = validate_flows(flows_dir, catalog_dir, flow_graph_path)
    if not result.valid:
        raise SystemExit(1)
