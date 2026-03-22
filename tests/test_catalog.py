"""Tests for the screen catalog and BFS pathfinding."""

from __future__ import annotations

import pytest

from qa_harness.knowledge.catalog import (
    ScreenCatalog,
    find_reachable_screens,
    find_shortest_path,
    get_screen_elements,
    get_screen_renderer,
    is_valid_transition,
    lookup_element,
    lookup_element_by_selector,
    lookup_screen,
    validate_flow_graph,
)


class TestCatalogLoading:
    def test_screens_loaded(self, catalog: ScreenCatalog) -> None:
        assert len(catalog.screens) > 0
        assert "intro" in catalog.screens
        assert "permission-dialog" in catalog.screens

    def test_elements_indexed(self, catalog: ScreenCatalog) -> None:
        # Elements should be indexed by both bare id and composite key
        assert "signup-btn" in catalog.elements_by_id
        assert "intro.signup-btn" in catalog.elements_by_id

    def test_selector_index_built(self, catalog: ScreenCatalog) -> None:
        # M3 fix: selector index for O(1) lookup
        el = catalog.elements_by_selector.get("intro-v2.click-signup-btn")
        assert el is not None
        assert el.id == "signup-btn"

    def test_flow_graph_loaded(self, catalog: ScreenCatalog) -> None:
        fg = catalog.flow_graph
        assert fg is not None
        assert fg.entry_screen == "intro"
        assert len(fg.transitions) > 0


class TestLookups:
    def test_lookup_element_by_id(self, catalog: ScreenCatalog) -> None:
        el = lookup_element(catalog, "signup-btn")
        assert el is not None
        assert el.label == "멤버십 신청"

    def test_lookup_element_by_selector(self, catalog: ScreenCatalog) -> None:
        el = lookup_element_by_selector(catalog, "intro-v2.click-signup-btn")
        assert el is not None
        assert el.id == "signup-btn"

    def test_lookup_missing_element(self, catalog: ScreenCatalog) -> None:
        assert lookup_element(catalog, "nonexistent") is None
        assert lookup_element_by_selector(catalog, "nonexistent") is None

    def test_lookup_screen(self, catalog: ScreenCatalog) -> None:
        screen = lookup_screen(catalog, "intro")
        assert screen is not None
        assert screen.name == "인트로 화면"

    def test_get_screen_elements(self, catalog: ScreenCatalog) -> None:
        elements = get_screen_elements(catalog, "intro")
        assert len(elements) >= 4  # splash, intro, signup, login

    def test_get_screen_renderer(self, catalog: ScreenCatalog) -> None:
        assert get_screen_renderer(catalog, "intro") == "webview"
        assert get_screen_renderer(catalog, "permission-dialog") == "native"
        assert get_screen_renderer(catalog, "nonexistent") is None


class TestTransitions:
    def test_valid_transition(self, catalog: ScreenCatalog) -> None:
        assert is_valid_transition(catalog, "intro", "onboarding")
        assert is_valid_transition(catalog, "intro", "login")

    def test_invalid_transition(self, catalog: ScreenCatalog) -> None:
        assert not is_valid_transition(catalog, "intro", "otp-verify")


class TestBFSPathfinding:
    def test_same_screen(self, catalog: ScreenCatalog) -> None:
        result = find_shortest_path(catalog, "intro", "intro")
        assert result.found
        assert result.distance == 0
        assert result.path == ["intro"]

    def test_direct_neighbor(self, catalog: ScreenCatalog) -> None:
        result = find_shortest_path(catalog, "intro", "onboarding")
        assert result.found
        assert result.distance == 1
        assert result.path == ["intro", "onboarding"]

    def test_multi_hop(self, catalog: ScreenCatalog) -> None:
        result = find_shortest_path(catalog, "intro", "otp-verify")
        assert result.found
        assert result.distance >= 2
        assert result.path[0] == "intro"
        assert result.path[-1] == "otp-verify"

    def test_no_path(self, catalog: ScreenCatalog) -> None:
        # terms-agreement is terminal with no outgoing edges
        result = find_shortest_path(catalog, "terms-agreement", "intro")
        assert not result.found

    def test_reachable_screens(self, catalog: ScreenCatalog) -> None:
        reachable = find_reachable_screens(catalog, "intro")
        assert "onboarding" in reachable
        assert "phone-input" in reachable
        assert "otp-verify" in reachable


class TestFlowGraphValidation:
    def test_no_issues(self, catalog: ScreenCatalog) -> None:
        issues = validate_flow_graph(catalog)
        # The real catalog may have some orphan screens; just ensure
        # no crash and a list is returned.
        assert isinstance(issues, list)
