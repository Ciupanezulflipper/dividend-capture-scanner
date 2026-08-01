#!/usr/bin/env bash
set -Eeuo pipefail

STATE_DIR="/var/lib/dqp-scanner"
TODAY_NY="$(TZ=America/New_York date +%F)"
MARKER_FILE="${STATE_DIR}/last_healthy_run_ny.txt"
ALERT_FILE="${STATE_DIR}/last_watchdog_alert_ny.txt"

last_healthy=""
last_alert=""
[[ -f "${MARKER_FILE}" ]] && last_healthy="$(tr -d '\r\n' < "${MARKER_FILE}")"
[[ -f "${ALERT_FILE}" ]] && last_alert="$(tr -d '\r\n' < "${ALERT_FILE}")"

if [[ "${last_healthy}" == "${TODAY_NY}" ]]; then
  exit 0
fi

if [[ "${last_alert}" == "${TODAY_NY}" ]]; then
  exit 0
fi

message="$(printf '⚠️ DQP MISSED HEALTHY RUN\nDate: %s\nExpected: 10:00 NY\nLast healthy marker: %s' "${TODAY_NY}" "${last_healthy:-none}")"

if [[ -z "${TELEGRAM_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "Watchdog cannot alert: Telegram credentials are missing." >&2
  exit 1
fi

curl -fsS --max-time 20 \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${message}" \
  "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" >/dev/null

printf '%s\n' "${TODAY_NY}" > "${ALERT_FILE}"
