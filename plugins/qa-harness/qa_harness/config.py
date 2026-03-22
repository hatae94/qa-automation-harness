"""Configuration management for the QA Automation Harness.

Loads settings from a YAML config file and/or CLI arguments.
All paths are resolved against the project root (fix: relative paths).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from qa_harness.types import HarnessConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_NAME = "qa-harness.yaml"


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from *start* looking for a sentinel file (pyproject.toml, .git,
    or qa-harness.yaml).  Falls back to cwd."""
    current = (start or Path.cwd()).resolve()
    sentinels = {"pyproject.toml", ".git", _DEFAULT_CONFIG_NAME}
    for parent in [current, *current.parents]:
        if any((parent / s).exists() for s in sentinels):
            return parent
    return Path.cwd().resolve()


def resolve_paths(cfg: HarnessConfig, root: Path) -> HarnessConfig:
    """Resolve every path field in *cfg* against *root*."""
    path_fields = [
        "catalog_dir",
        "templates_dir",
        "flow_graph_path",
        "output_dir",
        "reports_dir",
        "test_accounts_path",
    ]
    data = cfg.model_dump()
    for field in path_fields:
        raw = data.get(field, "")
        p = Path(raw)
        if not p.is_absolute():
            data[field] = str(root / p)
    # Also resolve cdp_bridge.input_server_path
    isp = data.get("cdp_bridge", {}).get("input_server_path", "")
    if isp and not Path(isp).is_absolute():
        data["cdp_bridge"]["input_server_path"] = str(root / isp)
    return HarnessConfig(**data)


def load_config(
    config_path: Path | None = None,
    *,
    overrides: dict | None = None,
) -> HarnessConfig:
    """Load configuration from YAML (optional) merged with CLI overrides.

    Priority: CLI overrides > YAML file > defaults.
    """
    root = find_project_root()
    data: dict = {}

    # Try loading YAML config
    candidates = [config_path] if config_path else [root / _DEFAULT_CONFIG_NAME]
    for candidate in candidates:
        if candidate and candidate.is_file():
            try:
                raw = candidate.read_text(encoding="utf-8")
                parsed = yaml.safe_load(raw)
                if isinstance(parsed, dict):
                    data = parsed
                    logger.info("Loaded config from %s", candidate)
                    break
            except yaml.YAMLError as exc:
                # C3 fix: surface YAML parse errors instead of silently ignoring
                raise RuntimeError(
                    f"Failed to parse config file {candidate}: {exc}"
                ) from exc

    # Merge CLI overrides
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    cfg = HarnessConfig(**data)
    cfg = resolve_paths(cfg, root)
    return cfg
