#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="/etc/dqp-scanner.env"
APP_DIR="/opt/dqp-scanner"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

read -r -p "Telegram chat ID: " TELEGRAM_CHAT_ID_INPUT
read -r -s -p "Telegram bot token: " TELEGRAM_TOKEN_INPUT
echo
read -r -p "Optional Healthchecks ping URL (press Enter to skip): " HEALTHCHECKS_PING_URL_INPUT

if [[ -z "${TELEGRAM_CHAT_ID_INPUT}" || -z "${TELEGRAM_TOKEN_INPUT}" ]]; then
  echo "Telegram chat ID and token are required." >&2
  exit 1
fi

if [[ "${TELEGRAM_CHAT_ID_INPUT}" =~ [[:space:]] || "${TELEGRAM_TOKEN_INPUT}" =~ [[:space:]] || "${HEALTHCHECKS_PING_URL_INPUT}" =~ [[:space:]] ]]; then
  echo "Credential and URL values must not contain whitespace." >&2
  exit 1
fi

umask 077
cat > "${ENV_FILE}" <<EOF_ENV
TELEGRAM_TOKEN=${TELEGRAM_TOKEN_INPUT}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID_INPUT}
WINDOW_DAYS=21
RSI_THRESHOLD=38
MA_LENGTH=200
SLEEP_SECONDS=1
MARKET_TIMEZONE=America/New_York
HISTORY_FILE=/var/lib/dqp-scanner/history.json
LOG_FILE=/var/log/dqp-scanner/stock_scan.log
HEALTHCHECKS_PING_URL=${HEALTHCHECKS_PING_URL_INPUT}
EOF_ENV

chmod 0600 "${ENV_FILE}"
systemctl daemon-reload

runuser -u dqp -- env \
  HISTORY_FILE=/var/lib/dqp-scanner/history.json \
  LOG_FILE=/var/log/dqp-scanner/stock_scan.log \
  "${APP_DIR}/.venv/bin/python" "${APP_DIR}/dividend_scanner.py" \
  --dry-run --no-telegram --limit 5 --show-all --force-weekend

systemctl enable --now dqp-scanner.timer dqp-watchdog.timer
systemctl list-timers --all 'dqp-*'
echo "Configuration complete. Dry-run passed and timers are enabled."
