#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/Ciupanezulflipper/dividend-capture-scanner.git"
REPO_REF="${DQP_REPO_REF:-main}"
APP_DIR="/opt/dqp-scanner"
STATE_DIR="/var/lib/dqp-scanner"
LOG_DIR="/var/log/dqp-scanner"
ENV_FILE="/etc/dqp-scanner.env"
SERVICE_USER="dqp"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git jq python3 python3-pip python3-venv tzdata

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "/home/${SERVICE_USER}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" fetch --prune origin
  git -C "${APP_DIR}" checkout "${REPO_REF}"
  git -C "${APP_DIR}" reset --hard "origin/${REPO_REF}"
else
  rm -rf "${APP_DIR}"
  git clone --branch "${REPO_REF}" --single-branch "${REPO_URL}" "${APP_DIR}"
fi

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${STATE_DIR}" "${STATE_DIR}/reports" "${LOG_DIR}"
chown -R root:root "${APP_DIR}"
chmod -R a+rX "${APP_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  cat > "${ENV_FILE}" <<'ENVEOF'
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
WINDOW_DAYS=21
RSI_THRESHOLD=38
MA_LENGTH=200
SLEEP_SECONDS=1
MARKET_TIMEZONE=America/New_York
HISTORY_FILE=/var/lib/dqp-scanner/history.json
LOG_FILE=/var/log/dqp-scanner/stock_scan.log
HEALTHCHECKS_PING_URL=
ENVEOF
  chmod 0600 "${ENV_FILE}"
fi

install -m 0755 "${APP_DIR}/deploy/oci/run-scanner.sh" /usr/local/sbin/dqp-run-scanner
install -m 0755 "${APP_DIR}/deploy/oci/watchdog.sh" /usr/local/sbin/dqp-watchdog
install -m 0644 "${APP_DIR}/deploy/oci/systemd/dqp-scanner.service" /etc/systemd/system/dqp-scanner.service
install -m 0644 "${APP_DIR}/deploy/oci/systemd/dqp-scanner.timer" /etc/systemd/system/dqp-scanner.timer
install -m 0644 "${APP_DIR}/deploy/oci/systemd/dqp-watchdog.service" /etc/systemd/system/dqp-watchdog.service
install -m 0644 "${APP_DIR}/deploy/oci/systemd/dqp-watchdog.timer" /etc/systemd/system/dqp-watchdog.timer

systemctl daemon-reload

echo "Bootstrap complete from ref ${REPO_REF}."
echo "Next: sudo bash ${APP_DIR}/deploy/oci/configure.sh"
