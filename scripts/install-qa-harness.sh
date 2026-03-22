#!/bin/bash
set -e

DATA_DIR="${CLAUDE_PLUGIN_DATA:-/tmp/qa-harness-data}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
mkdir -p "$DATA_DIR"

# Skip if already installed and up-to-date
if command -v qa-harness &>/dev/null; then
  # Check if version matches
  if diff -q "$PLUGIN_ROOT/pyproject.toml" "$DATA_DIR/pyproject.toml" &>/dev/null; then
    exit 0
  fi
fi

# Create venv in persistent data directory
if [ ! -d "$DATA_DIR/venv" ]; then
  python3 -m venv "$DATA_DIR/venv"
fi

# Activate and install (non-editable: editable breaks in plugin cache)
source "$DATA_DIR/venv/bin/activate"
pip install -q "$PLUGIN_ROOT"

# Cache version marker
cp "$PLUGIN_ROOT/pyproject.toml" "$DATA_DIR/pyproject.toml"

# Export PATH for this session
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo "export PATH=\"$DATA_DIR/venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  echo "export VIRTUAL_ENV=\"$DATA_DIR/venv\"" >> "$CLAUDE_ENV_FILE"
fi

exit 0
