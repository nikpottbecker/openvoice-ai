#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/phone-agent}"

cd "$APP_DIR"
"$APP_DIR/.venv/bin/pip" install -q -r requirements.txt
install -m 0644 systemd/phone-agent-dashboard.service /etc/systemd/system/phone-agent-dashboard.service
systemctl daemon-reload
systemctl enable --now phone-agent-dashboard.service
systemctl restart phone-agent-dashboard.service
curl -fsS http://127.0.0.1:8088/healthz
echo
systemctl --no-pager --full status phone-agent-dashboard.service | sed -n '1,12p'
