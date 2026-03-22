"""Screen Catalog -- App Knowledge Base.

Loads screen definitions from JSON, builds element indices,
and provides BFS shortest-path over the flow graph.

Fixes applied:
  M3  -- O(n) element lookup replaced with selector index
  C1  -- dict instead of Map
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from qa_harness.types import (
    AppScreen,
    FlowGraph,
    FlowTransition,
    RendererType,
    UIElement,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catalog data structure
# ---------------------------------------------------------------------------

@dataclass
class ScreenCatalog:
    """In-memory knowledge base for screens, elements, and the flow graph."""

    screens: dict[str, AppScreen] = field(default_factory=dict)
    # Keyed by element id and also by composite key "screen.element"
    elements_by_id: dict[str, UIElement] = field(default_factory=dict)
    # M3 fix: O(1) selector lookup via dedicated index
    elements_by_selector: dict[str, UIElement] = field(default_factory=dict)
    flow_graph: FlowGraph | None = None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_catalog(screens_dir: str | Path, flow_graph_path: str | Path) -> ScreenCatalog:
    """Load all screen JSON files and the flow graph, returning a
    fully indexed ``ScreenCatalog``."""
    screens_dir = Path(screens_dir)
    flow_graph_path = Path(flow_graph_path)

    catalog = ScreenCatalog()

    # -- screens --
    if not screens_dir.is_dir():
        logger.warning("Screens directory does not exist: %s", screens_dir)
    else:
        for json_file in sorted(screens_dir.glob("*.json")):
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                screen = AppScreen.model_validate(raw)
            except Exception as exc:
                logger.error("Failed to load screen %s: %s", json_file.name, exc)
                continue

            if not screen.id or not screen.name:
                logger.warning("Skipping invalid screen file: %s", json_file.name)
                continue

            catalog.screens[screen.id] = screen

            for element in screen.elements:
                composite = f"{screen.id}.{element.id}"
                catalog.elements_by_id[composite] = element
                # Bare id (last-write wins for duplicates across screens)
                catalog.elements_by_id[element.id] = element
                # Selector index (M3 fix)
                catalog.elements_by_selector[element.selector] = element

    # -- flow graph --
    if not flow_graph_path.is_file():
        logger.warning("Flow graph not found: %s", flow_graph_path)
    else:
        try:
            raw = json.loads(flow_graph_path.read_text(encoding="utf-8"))
            catalog.flow_graph = FlowGraph.model_validate(raw)
        except Exception as exc:
            logger.error("Failed to load flow graph: %s", exc)

    n_screens = len(catalog.screens)
    n_elements = len(catalog.elements_by_selector)
    n_trans = len(catalog.flow_graph.transitions) if catalog.flow_graph else 0
    logger.info(
        "Loaded %d screens, %d unique selectors, %d transitions",
        n_screens,
        n_elements,
        n_trans,
    )

    return catalog


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def lookup_element(catalog: ScreenCatalog, element_id: str) -> UIElement | None:
    """Look up an element by its id (bare or composite ``screen.element``)."""
    return catalog.elements_by_id.get(element_id)


def lookup_element_by_selector(catalog: ScreenCatalog, selector: str) -> UIElement | None:
    """O(1) selector lookup via the pre-built index (M3 fix)."""
    return catalog.elements_by_selector.get(selector)


def lookup_screen(catalog: ScreenCatalog, screen_id: str) -> AppScreen | None:
    return catalog.screens.get(screen_id)


def get_screen_elements(catalog: ScreenCatalog, screen_id: str) -> list[UIElement]:
    screen = catalog.screens.get(screen_id)
    return list(screen.elements) if screen else []


def get_screen_renderer(catalog: ScreenCatalog, screen_id: str) -> RendererType | None:
    screen = catalog.screens.get(screen_id)
    return screen.renderer_type if screen else None


def get_transitions_from(catalog: ScreenCatalog, screen_id: str) -> list[FlowTransition]:
    if not catalog.flow_graph:
        return []
    return [t for t in catalog.flow_graph.transitions if t.from_screen == screen_id]


def get_transitions_to(catalog: ScreenCatalog, screen_id: str) -> list[FlowTransition]:
    if not catalog.flow_graph:
        return []
    return [t for t in catalog.flow_graph.transitions if t.to_screen == screen_id]


def is_valid_transition(
    catalog: ScreenCatalog, from_screen: str, to_screen: str
) -> bool:
    if not catalog.flow_graph:
        return False
    return any(
        t.from_screen == from_screen and t.to_screen == to_screen
        for t in catalog.flow_graph.transitions
    )


# ---------------------------------------------------------------------------
# BFS pathfinding
# ---------------------------------------------------------------------------

@dataclass
class PathResult:
    found: bool
    path: list[str] = field(default_factory=list)
    transitions: list[FlowTransition] = field(default_factory=list)
    distance: int = -1


def find_shortest_path(
    catalog: ScreenCatalog, from_screen: str, to_screen: str
) -> PathResult:
    """BFS shortest path on the directed flow graph."""
    if from_screen == to_screen:
        return PathResult(found=True, path=[from_screen], transitions=[], distance=0)

    if not catalog.flow_graph:
        return PathResult(found=False)

    # Build adjacency list
    adj: dict[str, list[FlowTransition]] = {}
    for t in catalog.flow_graph.transitions:
        adj.setdefault(t.from_screen, []).append(t)

    visited: set[str] = {from_screen}
    queue: deque[tuple[list[str], list[FlowTransition]]] = deque()
    queue.append(([from_screen], []))

    while queue:
        path, transitions = queue.popleft()
        current = path[-1]
        for t in adj.get(current, []):
            if t.to_screen in visited:
                continue
            new_path = [*path, t.to_screen]
            new_trans = [*transitions, t]
            if t.to_screen == to_screen:
                return PathResult(
                    found=True,
                    path=new_path,
                    transitions=new_trans,
                    distance=len(new_path) - 1,
                )
            visited.add(t.to_screen)
            queue.append((new_path, new_trans))

    return PathResult(found=False)


def find_reachable_screens(catalog: ScreenCatalog, from_screen: str) -> set[str]:
    """All screens reachable from *from_screen* via BFS."""
    if not catalog.flow_graph:
        return {from_screen}

    adj: dict[str, list[str]] = {}
    for t in catalog.flow_graph.transitions:
        adj.setdefault(t.from_screen, []).append(t.to_screen)

    reachable: set[str] = {from_screen}
    queue: deque[str] = deque([from_screen])
    while queue:
        current = queue.popleft()
        for neighbor in adj.get(current, []):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)
    return reachable


def validate_flow_graph(catalog: ScreenCatalog) -> list[str]:
    """Return a list of consistency issues with the flow graph."""
    issues: list[str] = []
    fg = catalog.flow_graph
    if not fg:
        issues.append("No flow graph loaded")
        return issues

    if fg.entry_screen not in catalog.screens:
        issues.append(f'Entry screen "{fg.entry_screen}" not found in catalog')

    for ts in fg.terminal_screens:
        if ts not in catalog.screens:
            issues.append(f'Terminal screen "{ts}" not found in catalog')

    for t in fg.transitions:
        if t.from_screen not in catalog.screens:
            issues.append(f'Transition source "{t.from_screen}" not found')
        if t.to_screen not in catalog.screens:
            issues.append(f'Transition target "{t.to_screen}" not found')

    if fg.entry_screen in catalog.screens:
        reachable = find_reachable_screens(catalog, fg.entry_screen)
        for sid in catalog.screens:
            if sid not in reachable:
                issues.append(f'Screen "{sid}" is not reachable from entry')

    return issues
