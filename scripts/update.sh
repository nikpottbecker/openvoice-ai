#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/phone-agent"
cd "$APP_DIR"

if [[ -d .git ]]; then
  git pull --ff-only
fi

.venv/bin/pip install -r requirements.txt
sudo systemctl restart asterisk
sudo "$APP_DIR/scripts/healthcheck.sh"
