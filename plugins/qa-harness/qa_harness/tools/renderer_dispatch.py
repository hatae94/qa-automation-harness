"""Renderer Dispatch -- Determine WebView vs Native for each screen.

Detection method: catalog metadata is the source of truth.
Live hierarchy can cross-check via the WebView marker
(testID=src.web-container).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from qa_harness.types import AppScreen, RendererType, UIElement

logger = logging.getLogger(__name__)

WEBVIEW_MARKER = "src.web-container"
NATIVE_INDICATORS = (
    "com.android.permissioncontroller",
    "android.widget.AlertDialog",
    "com.google.android.apps.photos",
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class RendererDispatchResult:
    screen_id: str
    renderer_type: RendererType
    confidence: str  # "catalog" | "hierarchy-detected" | "inferred"
    reason: str


@dataclass
class FlowRendererStep:
    step_index: int
    screen_id: str
    renderer_type: RendererType
    interaction_method: str  # cdp-tap | cdp-input | native-tap | native-input | none


@dataclass
class FlowRendererMetadata:
    flow_id: str
    steps: list[FlowRendererStep]


# ---------------------------------------------------------------------------
# Hierarchy-based detection
# ---------------------------------------------------------------------------

def detect_renderer_from_hierarchy(hierarchy: dict[str, Any]) -> RendererType:
    """Detect renderer type from a maestro hierarchy dump."""
    if _contains_marker(hierarchy, "testID", WEBVIEW_MARKER):
        return "webview"
    if _contains_native_indicator(hierarchy):
        return "native"
    return "native"


def _contains_marker(node: dict, key: str, value: str) -> bool:
    if node.get(key) == value:
        return True
    for child in node.get("children", []):
        if _contains_marker(child, key, value):
            return True
    return False


def _contains_native_indicator(node: dict) -> bool:
    cn = node.get("className", "")
    if any(ind in cn for ind in NATIVE_INDICATORS):
        return True
    for child in node.get("children", []):
        if _contains_native_indicator(child):
            return True
    return False


# ---------------------------------------------------------------------------
# Catalog-based dispatch
# ---------------------------------------------------------------------------

def get_renderer_from_catalog(screen: AppScreen) -> RendererDispatchResult:
    return RendererDispatchResult(
        screen_id=screen.id,
        renderer_type=screen.renderer_type,
        confidence="catalog",
        reason=f"Defined in catalog: {screen.renderer_type}",
    )


def dispatch_all_screens(catalog_dir: Path) -> list[RendererDispatchResult]:
    """Determine renderer type for all screens in the catalog directory."""
    results: list[RendererDispatchResult] = []
    for jf in sorted(catalog_dir.glob("*.json")):
        try:
            raw = json.loads(jf.read_text(encoding="utf-8"))
            screen = AppScreen.model_validate(raw)
            results.append(get_renderer_from_catalog(screen))
        except Exception as exc:
            logger.warning("Failed to load screen %s: %s", jf.name, exc)
    return results


# ---------------------------------------------------------------------------
# Flow metadata generation
# ---------------------------------------------------------------------------

def generate_flow_renderer_metadata(
    flow_id: str,
    screen_sequence: list[tuple[int, str]],
    screen_catalog: dict[str, AppScreen],
) -> FlowRendererMetadata:
    steps: list[FlowRendererStep] = []
    for step_idx, screen_id in screen_sequence:
        screen = screen_catalog.get(screen_id)
        rt: RendererType = screen.renderer_type if screen else "native"
        method = "cdp-tap" if rt == "webview" else "native-tap"
        steps.append(FlowRendererStep(
            step_index=step_idx,
            screen_id=screen_id,
            renderer_type=rt,
            interaction_method=method,
        ))
    return FlowRendererMetadata(flow_id=flow_id, steps=steps)


def is_hybrid_flow(metadata: FlowRendererMetadata) -> bool:
    renderers = {s.renderer_type for s in metadata.steps}
    return len(renderers) > 1


def get_interaction_method(
    element: UIElement, screen_renderer: RendererType
) -> str:
    if element.renderer_type == "native" or screen_renderer == "native":
        return "native-input" if element.type.value == "input" else "native-tap"
    return "cdp-input" if element.type.value == "input" else "cdp-tap"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command("dispatch")
@click.option("--catalog", "catalog_dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--hierarchy", "hierarchy_path", default=None, type=click.Path(path_type=Path))
def dispatch_cmd(catalog_dir: Path, hierarchy_path: Path | None) -> None:
    """Analyze renderer types for all cataloged screens."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    results = dispatch_all_screens(catalog_dir)

    click.echo("\nScreen Renderer Map:")
    click.echo("-" * 60)
    for r in results:
        tag = "WEB" if r.renderer_type == "webview" else "NAT"
        click.echo(f"  [{tag}] {r.screen_id:<25} {r.renderer_type:<10} ({r.confidence})")
    click.echo("-" * 60)

    web = sum(1 for r in results if r.renderer_type == "webview")
    nat = sum(1 for r in results if r.renderer_type == "native")
    click.echo(f"\nSummary: {web} WebView, {nat} Native screens")

    if hierarchy_path and hierarchy_path.is_file():
        click.echo(f"\nCross-checking with hierarchy: {hierarchy_path}")
        raw = json.loads(hierarchy_path.read_text(encoding="utf-8"))
        detected = detect_renderer_from_hierarchy(raw)
        click.echo(f"Live hierarchy detection: {detected}")
