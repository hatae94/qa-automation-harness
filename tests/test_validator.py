"""Tests for the YAML validator."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from qa_harness.knowledge.catalog import ScreenCatalog
from qa_harness.tools.yaml_validator import validate_flows


@pytest.fixture()
def flows_dir(tmp_path: Path) -> Path:
    d = tmp_path / "flows"
    d.mkdir()
    return d


class TestValidateFlows:
    def _write_flow(self, flows_dir: Path, name: str, content: str) -> Path:
        p = flows_dir / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_valid_flow(self, flows_dir: Path, catalog: ScreenCatalog) -> None:
        content = textwrap.dedent("""\
            # TC IDs: LoginPage_1
            appId: com.cupist.alphaz
            ---
            - launchApp:
                appId: com.cupist.alphaz
            - assertVisible:
                id: "intro-v2.click-signup-btn"
        """)
        self._write_flow(flows_dir, "flow_test.yaml", content)
        fg = catalog.flow_graph
        assert fg is not None
        # Use the real catalog dir and flow graph path
        from tests.conftest import SCREENS_DIR, FLOW_GRAPH_PATH
        result = validate_flows(flows_dir, SCREENS_DIR, FLOW_GRAPH_PATH)
        assert result.stats.total_flows == 1

    def test_unknown_command_flagged(self, flows_dir: Path) -> None:
        content = textwrap.dedent("""\
            ---
            - fakeCommand:
                id: "something"
        """)
        self._write_flow(flows_dir, "bad_cmd.yaml", content)
        from tests.conftest import SCREENS_DIR, FLOW_GRAPH_PATH
        result = validate_flows(flows_dir, SCREENS_DIR, FLOW_GRAPH_PATH)
        codes = [i.code for i in result.issues]
        assert "UNKNOWN_COMMAND" in codes

    def test_unfilled_slot_flagged(self, flows_dir: Path) -> None:
        content = textwrap.dedent("""\
            ---
            - tapOn:
                text: "{{unfilled}}"
        """)
        self._write_flow(flows_dir, "unfilled.yaml", content)
        from tests.conftest import SCREENS_DIR, FLOW_GRAPH_PATH
        result = validate_flows(flows_dir, SCREENS_DIR, FLOW_GRAPH_PATH)
        codes = [i.code for i in result.issues]
        assert "UNFILLED_SLOT" in codes

    def test_empty_flow_warning(self, flows_dir: Path) -> None:
        """M7 fix: files with no steps should produce a warning."""
        content = textwrap.dedent("""\
            appId: com.cupist.alphaz
            ---
        """)
        self._write_flow(flows_dir, "empty.yaml", content)
        from tests.conftest import SCREENS_DIR, FLOW_GRAPH_PATH
        result = validate_flows(flows_dir, SCREENS_DIR, FLOW_GRAPH_PATH)
        codes = [i.code for i in result.issues]
        assert "EMPTY_FLOW" in codes

    def test_missing_script_file_error(self, flows_dir: Path) -> None:
        content = textwrap.dedent("""\
            ---
            - runScript:
                env:
                  DEVICE: emulator-5554
        """)
        self._write_flow(flows_dir, "no_file.yaml", content)
        from tests.conftest import SCREENS_DIR, FLOW_GRAPH_PATH
        result = validate_flows(flows_dir, SCREENS_DIR, FLOW_GRAPH_PATH)
        codes = [i.code for i in result.issues]
        assert "MISSING_SCRIPT_FILE" in codes
