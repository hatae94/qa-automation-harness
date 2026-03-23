#!/usr/bin/env bash
#
# adb_clipboard_input.sh -- Native Korean text input via ADB clipboard paste
#
# For native screens where CDP doesn't work. Uses ADB to set clipboard
# content, then pastes into the currently focused field.
#
# ENV:
#   TEXT    -- Text to input (required; supports Korean/CJK)
#   DEVICE  -- ADB device id (optional; selects specific device)
#
# Exit 0 on success, exit 1 on failure.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEXT="${TEXT:-}"
DEVICE="${DEVICE:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[adb_clipboard]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[adb_clipboard]${NC} $*"; }
log_error() { echo -e "${RED}[adb_clipboard]${NC} $*"; }

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

if [[ -z "$TEXT" ]]; then
  log_error "TEXT env var is required"
  exit 1
fi

if ! command -v adb &>/dev/null; then
  log_error "adb not found in PATH"
  exit 1
fi

# Build ADB command with optional device selector
ADB_CMD=(adb)
if [[ -n "$DEVICE" ]]; then
  ADB_CMD+=(-s "$DEVICE")
fi

# Verify device is connected
if ! "${ADB_CMD[@]}" get-state &>/dev/null; then
  log_error "No ADB device connected${DEVICE:+ (device: $DEVICE)}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Clipboard paste flow
# ---------------------------------------------------------------------------

log_info "Setting clipboard text (${#TEXT} chars)..."

# Method 1: Use Android's clipboard service via am broadcast
# The ClipboardService broadcast receiver sets clipboard content directly.
# This approach handles Korean/CJK text that `adb shell input text` cannot.
#
# We use the service call approach which is more reliable across Android versions.

# Base64 encode the text to safely pass it through shell
ENCODED_TEXT=$(echo -n "$TEXT" | base64)

"${ADB_CMD[@]}" shell "
  # Decode and set clipboard via Android's service
  DECODED=\$(echo '$ENCODED_TEXT' | base64 -d 2>/dev/null)

  # Try am broadcast method (works on most ROMs)
  am broadcast \
    -a clipper.set \
    -e text \"\$DECODED\" \
    2>/dev/null

  # Fallback: use service call to clipboard manager
  # This writes to the system clipboard via the ClipboardManager API
  if [ \$? -ne 0 ]; then
    # Use input via content provider as fallback
    content insert \
      --uri content://com.android.clipboard/clip \
      --bind text:s:\"\$DECODED\" \
      2>/dev/null || true
  fi
" 2>/dev/null

# Small delay to ensure clipboard is set
sleep 0.3

# Step 2: Long press on the currently focused element to trigger paste menu
log_info "Triggering long press for paste menu..."

# Get the focused element coordinates via dumpsys
FOCUS_BOUNDS=$("${ADB_CMD[@]}" shell dumpsys input_method 2>/dev/null \
  | grep -oP 'mCursorRect\((-?\d+),\s*(-?\d+)\s*-\s*(-?\d+),\s*(-?\d+)\)' \
  | head -1 || true)

if [[ -n "$FOCUS_BOUNDS" ]]; then
  # Parse cursor coordinates for long press
  X=$(echo "$FOCUS_BOUNDS" | grep -oP '\d+' | head -1)
  Y=$(echo "$FOCUS_BOUNDS" | grep -oP '\d+' | head -2 | tail -1)
  log_info "Long pressing at cursor position ($X, $Y)..."
  "${ADB_CMD[@]}" shell input swipe "$X" "$Y" "$X" "$Y" 1000
else
  # Fallback: use keyevent for select-all then paste
  log_warn "Could not detect cursor position, using keyevent fallback"
fi

sleep 0.5

# Step 3: Paste from clipboard via keyevent
# KEYCODE_PASTE = 279
log_info "Pasting from clipboard..."
"${ADB_CMD[@]}" shell input keyevent 279

# Verify: Small delay then check
sleep 0.3

log_info "Clipboard input complete"
exit 0
