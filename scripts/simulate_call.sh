#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/phone-agent"
cd "$APP_DIR"
export PYTHONPATH="$APP_DIR/src"
exec "$APP_DIR/.venv/bin/python" -m phone_agent.simulate_call "$@"
