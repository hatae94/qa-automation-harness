#!/bin/bash
set -e

DATA_DIR="${CLAUDE_PLUGIN_DATA:-/tmp/qa-harness-data}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
mkdir -p "$DATA_DIR"

# Check if already installed and up-to-date (compare plugin.json version)
INSTALLED_VER=""
if [ -f "$DATA_DIR/.installed_version" ]; then
  INSTALLED_VER=$(cat "$DATA_DIR/.installed_version")
fi
PLUGIN_VER=$(python3 -c "import json; print(json.load(open('$PLUGIN_ROOT/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")

if [ "$INSTALLED_VER" = "$PLUGIN_VER" ] && [ -f "$DATA_DIR/venv/bin/qa-harness" ]; then
  exit 0
fi

# Create venv if needed
if [ ! -d "$DATA_DIR/venv" ]; then
  python3 -m venv "$DATA_DIR/venv"
fi

# Activate and force reinstall to pick up new code
source "$DATA_DIR/venv/bin/activate"
pip install -q --force-reinstall "$PLUGIN_ROOT"

# Record installed version
echo "$PLUGIN_VER" > "$DATA_DIR/.installed_version"

# Export PATH for this session
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo "export PATH=\"$DATA_DIR/venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  echo "export VIRTUAL_ENV=\"$DATA_DIR/venv\"" >> "$CLAUDE_ENV_FILE"
fi

exit 0
