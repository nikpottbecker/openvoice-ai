#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/phone-agent"
cd "$APP_DIR"

test -f .env
test -x .venv/bin/python
export PYTHONPATH="$APP_DIR/src"
.venv/bin/python -m compileall -q src
.venv/bin/python - <<'PY'
from phone_agent.config import get_settings
s = get_settings()
assert s.openrouter_api_key, "OPENROUTER_API_KEY missing"
assert s.piper_model.exists(), "Piper model missing"
assert s.piper_config.exists(), "Piper config missing"
PY

asterisk -s /run/asterisk/asterisk.ctl -rx "core show version" >/dev/null
asterisk -s /run/asterisk/asterisk.ctl -rx "pjsip show registrations" || true

echo "phone-agent healthcheck ok"
