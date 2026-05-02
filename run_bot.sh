#!/usr/bin/env bash
# =============================================================================
# run_bot.sh — Dividend Capture Scanner Launcher
# =============================================================================
# Handles dependency install, optional dependency attempts, syntax check,
# and execution of dividend_scanner.py.
#
# Usage:
#   ./run_bot.sh --dry-run --limit 10 --show-all
#
# Termux:
#   Auto-detected when PREFIX contains com.termux.
#   You may also force it manually:
#     TERMUX_MODE=1 ./run_bot.sh --dry-run --limit 10 --show-all
#
# Linux VPS:
#   Uses .venv automatically unless TERMUX_MODE=1 is set.
#
# Cron target:
#   CRON_TZ=America/New_York
#   0 10 * * 1-5 cd /path/to/dividend-capture-scanner && ./run_bot.sh >> cron_dividend_bot.log 2>&1
#
# v1 limitation:
#   Does not skip NYSE holidays.
# =============================================================================

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
REQ_FILE="requirements.txt"
MAIN_SCRIPT="dividend_scanner.py"
TERMUX_STAMP=".termux_req_sha256"
LINUX_STAMP="$VENV_DIR/.req_sha256"

# Auto-detect Termux unless TERMUX_MODE is already set by the user.
if [ -z "${TERMUX_MODE+x}" ]; then
  if [ -n "${PREFIX:-}" ] && printf '%s' "$PREFIX" | grep -q 'com.termux'; then
    TERMUX_MODE=1
  else
    TERMUX_MODE=0
  fi
fi

if [ "${TERMUX_MODE:-0}" = "1" ]; then
  MODE_LABEL="Termux (no venv)"
  STAMP_FILE="$TERMUX_STAMP"
else
  MODE_LABEL="Linux venv"
  STAMP_FILE="$LINUX_STAMP"
fi

log()  { echo "[run_bot] $*"; }
warn() { echo "[run_bot] WARN: $*"; }
die()  { echo "[run_bot] ERROR: $*" >&2; exit 1; }
pass() { echo "[run_bot] PASS: $*"; }

echo ""
echo "====================================================="
echo "  Dividend Capture Scanner — Launcher"
echo "====================================================="
echo "  Dir:  $SCRIPT_DIR"
echo "  Mode: $MODE_LABEL"
echo "====================================================="
echo ""

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 not found. Termux: pkg install python"

[ -f "$MAIN_SCRIPT" ] || die "$MAIN_SCRIPT not found in $SCRIPT_DIR"
[ -f "$REQ_FILE" ] || die "$REQ_FILE not found in $SCRIPT_DIR"

if [ ! -f ".env" ]; then
  warn ".env not found — Telegram alerts will not fire."
  warn "For dry-run smoke tests this is acceptable."
fi

requirements_hash() {
  "$PYTHON_BIN" -c "
import hashlib
from pathlib import Path
path = Path('$REQ_FILE')
print(hashlib.sha256(path.read_bytes()).hexdigest())
"
}

try_optional() {
  local pkg="$1"
  local label="${2:-$1}"

  log "Optional: installing $label ..."
  if "${PIP_BASE[@]}" install "${PIP_FLAGS[@]}" "$pkg" >/dev/null 2>&1; then
    pass "$label installed."
  else
    warn "$label unavailable — built-in fallback will be used."
  fi
}

CURRENT_HASH="$(requirements_hash)"
INSTALLED_HASH=""
[ -f "$STAMP_FILE" ] && INSTALLED_HASH="$(cat "$STAMP_FILE")"

if [ "${TERMUX_MODE:-0}" = "1" ]; then
  log "Running in Termux mode."

  PIP_BASE=("$PYTHON_BIN" -m pip)
  PIP_FLAGS=(--break-system-packages -q)

  "${PIP_BASE[@]}" install "${PIP_FLAGS[@]}" --upgrade pip setuptools wheel \
    || warn "pip upgrade failed or was unnecessary; continuing."

  if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
    log "Installing core dependencies from $REQ_FILE ..."
    "${PIP_BASE[@]}" install "${PIP_FLAGS[@]}" -r "$REQ_FILE" \
      || die "Core dependency install failed. Check requirements.txt."

    pass "Core dependencies installed."

    try_optional "lxml>=5.0,<7" "lxml faster HTML parser"
    try_optional "pandas-ta>=0.3.14b0" "pandas-ta preferred RSI engine"

    printf "%s" "$CURRENT_HASH" > "$STAMP_FILE"
    pass "Dependency stamp written to $STAMP_FILE"
  else
    pass "Dependencies already up to date according to $STAMP_FILE."
  fi

  log "Syntax check..."
  "$PYTHON_BIN" -m py_compile "$MAIN_SCRIPT" || die "Syntax error in $MAIN_SCRIPT"
  pass "Syntax OK."

  echo ""
  log "Starting scanner with args: ${*:-<none>}"
  echo ""
  exec "$PYTHON_BIN" "$MAIN_SCRIPT" "$@"

else
  log "Running in Linux venv mode."

  if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment at $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR" \
      || die "venv creation failed. Install python3-venv or run with TERMUX_MODE=1."
    pass "Virtual environment created."
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  PIP_BASE=(python -m pip)
  PIP_FLAGS=(-q)

  "${PIP_BASE[@]}" install "${PIP_FLAGS[@]}" --upgrade pip setuptools wheel \
    || warn "pip upgrade failed or was unnecessary; continuing."

  if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
    log "Installing core dependencies from $REQ_FILE ..."
    "${PIP_BASE[@]}" install "${PIP_FLAGS[@]}" -r "$REQ_FILE" \
      || { deactivate; die "Core dependency install failed. Check requirements.txt."; }

    pass "Core dependencies installed."

    try_optional "lxml>=5.0,<7" "lxml faster HTML parser"
    try_optional "pandas-ta>=0.3.14b0" "pandas-ta preferred RSI engine"

    printf "%s" "$CURRENT_HASH" > "$STAMP_FILE"
    pass "Dependency stamp written to $STAMP_FILE"
  else
    pass "Dependencies already match $REQ_FILE."
  fi

  log "Syntax check..."
  python -m py_compile "$MAIN_SCRIPT" \
    || { deactivate; die "Syntax error in $MAIN_SCRIPT"; }
  pass "Syntax OK."

  echo ""
  log "Starting scanner with args: ${*:-<none>}"
  echo ""
  python "$MAIN_SCRIPT" "$@"
  exit_code=$?

  deactivate

  echo ""
  if [ "$exit_code" -eq 0 ]; then
    pass "Scanner finished cleanly."
  else
    warn "Scanner exited with code $exit_code. Check stock_scan.log."
  fi

  exit "$exit_code"
fi
