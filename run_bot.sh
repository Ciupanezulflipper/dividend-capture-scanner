#!/usr/bin/env bash
# =============================================================================
# run_bot.sh — Dividend Quality Pullback Scanner launcher
# =============================================================================
# Routine scheduled runs are deliberately network-free until the scanner starts.
# Dependency installation is explicit:
#
#   ./run_bot.sh --install-deps
#
# Normal scanner arguments are passed through unchanged:
#
#   ./run_bot.sh --dry-run --limit 10 --show-all --force-weekend
# =============================================================================

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
REQ_FILE="requirements.txt"
MAIN_SCRIPT="dividend_scanner.py"
RUNNER_SCRIPT="tools/run_production_scan.py"
TERMUX_STAMP=".termux_req_sha256"
LINUX_STAMP="$VENV_DIR/.req_sha256"

if [ -z "${TERMUX_MODE+x}" ]; then
  if [ -n "${PREFIX:-}" ] && printf '%s' "$PREFIX" | grep -q 'com.termux'; then
    TERMUX_MODE=1
  else
    TERMUX_MODE=0
  fi
fi

log()  { printf '[run_bot] %s\n' "$*"; }
warn() { printf '[run_bot] WARN: %s\n' "$*" >&2; }
die()  { printf '[run_bot] ERROR: %s\n' "$*" >&2; exit 1; }
pass() { printf '[run_bot] PASS: %s\n' "$*"; }

requirements_hash() {
  "$PYTHON_BIN" -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())'
}

install_dependencies() {
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 not found"

  if [ "${TERMUX_MODE:-0}" = "1" ]; then
    log "Installing Termux core dependencies from $REQ_FILE ..."
    "$PYTHON_BIN" -m pip install --break-system-packages -r "$REQ_FILE" \
      || die "Core dependency installation failed"
    printf '%s' "$(requirements_hash)" > "$TERMUX_STAMP"
  else
    if [ ! -d "$VENV_DIR" ]; then
      log "Creating virtual environment at $VENV_DIR ..."
      "$PYTHON_BIN" -m venv "$VENV_DIR" \
        || die "venv creation failed; install python3-venv"
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    python -m pip install -r "$REQ_FILE" \
      || { deactivate; die "Core dependency installation failed"; }
    printf '%s' "$(python -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())')" \
      > "$LINUX_STAMP"
    deactivate
  fi
  pass "Core dependencies installed. No optional packages were attempted."
}

if [ "${1:-}" = "--install-deps" ]; then
  shift
  [ "$#" -eq 0 ] || die "--install-deps cannot be combined with scanner arguments"
  install_dependencies
  exit 0
fi

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 not found"
[ -f "$MAIN_SCRIPT" ] || die "$MAIN_SCRIPT not found in $SCRIPT_DIR"
[ -f "$RUNNER_SCRIPT" ] || die "$RUNNER_SCRIPT not found in $SCRIPT_DIR"
[ -f "$REQ_FILE" ] || die "$REQ_FILE not found in $SCRIPT_DIR"

if [ "${TERMUX_MODE:-0}" = "1" ]; then
  MODE_LABEL="Termux (system Python)"
  STAMP_FILE="$TERMUX_STAMP"
else
  MODE_LABEL="Linux virtual environment"
  STAMP_FILE="$LINUX_STAMP"
  [ -x "$VENV_DIR/bin/python" ] \
    || die "Missing $VENV_DIR. Run ./run_bot.sh --install-deps once."
  PYTHON_BIN="$VENV_DIR/bin/python"
fi

printf '\n=====================================================\n'
printf '  Dividend Quality Pullback Scanner — Launcher\n'
printf '=====================================================\n'
printf '  Dir:  %s\n' "$SCRIPT_DIR"
printf '  Mode: %s\n' "$MODE_LABEL"
printf '=====================================================\n\n'

CURRENT_HASH="$(requirements_hash)"
INSTALLED_HASH=""
[ -f "$STAMP_FILE" ] && INSTALLED_HASH="$(cat "$STAMP_FILE")"
if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
  warn "Dependency stamp is missing or stale. No automatic network install will run."
  warn "Run ./run_bot.sh --install-deps during a supervised maintenance window."
fi

"$PYTHON_BIN" -c 'import bs4, dotenv, html5lib, pandas, requests, rich, tabulate, yfinance' \
  || die "A required Python package is missing. Run ./run_bot.sh --install-deps."
pass "Required Python imports available."

"$PYTHON_BIN" -m py_compile "$MAIN_SCRIPT" "$RUNNER_SCRIPT" \
  || die "Python syntax validation failed"
pass "Python syntax OK."

log "Starting production wrapper with scanner args: ${*:-<none>}"
exec "$PYTHON_BIN" "$RUNNER_SCRIPT" "$@"
