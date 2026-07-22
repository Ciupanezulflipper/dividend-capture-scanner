#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/dqp-scanner"
STATE_DIR="/var/lib/dqp-scanner"
TODAY_NY="$(TZ=America/New_York date +%F)"
REPORT_DIR="${STATE_DIR}/reports/us_market_$(TZ=America/New_York date +%Y%m%d)"
HEALTH_FILE="${REPORT_DIR}/scan_health_${TODAY_NY}.json"
MARKER_FILE="${STATE_DIR}/last_healthy_run_ny.txt"

mkdir -p "${REPORT_DIR}"
cd "${APP_DIR}"

set +e
"${APP_DIR}/.venv/bin/python" "${APP_DIR}/dividend_scanner.py" \
  --report \
  --telegram-clean-only \
  --daily-heartbeat \
  --report-dir "${REPORT_DIR}"
scanner_rc=$?
set -e

healthy=false
if [[ "${scanner_rc}" -eq 0 && -f "${HEALTH_FILE}" ]]; then
  if jq -e '.is_collapsed == false' "${HEALTH_FILE}" >/dev/null 2>&1; then
    healthy=true
  fi
fi

if [[ "${healthy}" == true ]]; then
  printf '%s\n' "${TODAY_NY}" > "${MARKER_FILE}"
  if [[ -n "${HEALTHCHECKS_PING_URL:-}" ]]; then
    curl -fsS --max-time 15 "${HEALTHCHECKS_PING_URL}" >/dev/null || true
  fi
  exit 0
fi

if [[ -n "${HEALTHCHECKS_PING_URL:-}" ]]; then
  curl -fsS --max-time 15 "${HEALTHCHECKS_PING_URL}/fail" >/dev/null || true
fi

if [[ "${scanner_rc}" -ne 0 ]]; then
  exit "${scanner_rc}"
fi
exit 1
