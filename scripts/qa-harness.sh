#!/usr/bin/env bash
#
# QA Automation Harness -- Shell Wrapper
#
# Usage:
#   qa-harness parse-tc -i <csv> -o <json>
#   qa-harness generate-yaml --tc <json> ...
#   qa-harness validate --flows <dir> --catalog <dir>
#   qa-harness run --flows <dir> [--dry-run]
#   qa-harness report --tc-map <json> --output <dir>
#   qa-harness full -i <csv> [--dry-run]
#   qa-harness cdp <start|stop|status|health|clean>
#   qa-harness dispatch --catalog <dir>
#
# Fix: set -e properly handled; dry-run passed through correctly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[harness]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[harness]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[harness]${NC} $*"; }
log_error() { echo -e "${RED}[harness]${NC} $*"; }

# Detect Python command
find_python() {
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      PYTHON="$cmd"
      return 0
    fi
  done
  log_error "Python 3.11+ not found."
  exit 1
}

find_python

# Check if package is installed (look for entry point or run as module)
run_harness() {
  if command -v qa-harness &>/dev/null; then
    qa-harness "$@"
  else
    $PYTHON -m qa_harness.cli "$@"
  fi
}

case "${1:-help}" in
  help|--help|-h)
    echo "QA Automation Harness"
    echo ""
    echo "Usage: qa-harness <command> [options]"
    echo ""
    echo "Commands:"
    echo "  parse-tc        Parse TC CSV into normalized JSON"
    echo "  generate-yaml   Generate YAML from parsed TCs"
    echo "  validate        Validate all generated YAML"
    echo "  run             Execute via maestro-runner"
    echo "  report          Generate report"
    echo "  full            Full pipeline"
    echo "  cdp             Manage CDP bridge (start|stop|status|health|clean)"
    echo "  dispatch        Show screen renderer types"
    echo ""
    ;;
  *)
    run_harness "$@"
    ;;
esac
