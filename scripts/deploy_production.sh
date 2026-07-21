#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/phone-agent}"
BRANCH="${BRANCH:-main}"
BACKUP_ROOT="${BACKUP_ROOT:-$APP_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the production LXC: sudo bash scripts/deploy_production.sh"
  exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "== Backup: $BACKUP_DIR"
tar -C / -czf "$BACKUP_DIR/asterisk.tgz" etc/asterisk || true
tar -C / -czf "$BACKUP_DIR/systemd-phone-agent.tgz" \
  etc/systemd/system/phone-agent-dashboard.service \
  etc/systemd/system/phone-agent-health.service \
  etc/systemd/system/phone-agent-health.timer 2>/dev/null || true
tar -C "$APP_DIR" -czf "$BACKUP_DIR/config-and-data.tgz" \
  .env config dashboard transcripts logs 2>/dev/null || true
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" rev-parse HEAD >"$BACKUP_DIR/git-head.txt"
fi

cat >"$BACKUP_DIR/rollback.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$APP_DIR"
BACKUP_DIR="$BACKUP_DIR"
bash "\$APP_DIR/scripts/rollback_production.sh" "\$BACKUP_DIR"
EOF
chmod 0755 "$BACKUP_DIR/rollback.sh"

echo "== Update repository"
cd "$APP_DIR"
if [[ -d .git ]]; then
  git fetch origin "$BRANCH"
  git pull --ff-only origin "$BRANCH"
fi

echo "== Python dependencies and syntax"
.venv/bin/pip install -q -r requirements.txt
export PYTHONPATH="$APP_DIR/src"
.venv/bin/python -m compileall -q src

echo "== Validate runtime configuration"
.venv/bin/python - <<'PY'
from phone_agent.config import get_settings, load_runtime_settings
from phone_agent.menu import load_menu_config
from phone_agent.tts_config import load_tts_config

s = get_settings()
load_runtime_settings(s)
load_menu_config(s.config_dir / "phone_menu.json")
load_tts_config()
assert s.whisper_language == "de", "whisper_language must stay de for German phone calls"
print("config ok")
PY

echo "== Install units and permissions"
install -m 0644 systemd/phone-agent-dashboard.service /etc/systemd/system/phone-agent-dashboard.service
install -m 0644 systemd/phone-agent-health.service /etc/systemd/system/phone-agent-health.service
install -m 0644 systemd/phone-agent-health.timer /etc/systemd/system/phone-agent-health.timer
chmod 0755 scripts/healthcheck.sh scripts/production_audit.sh scripts/rollback_production.sh
if getent passwd asterisk >/dev/null 2>&1; then
  chown -R asterisk:asterisk "$APP_DIR/logs" "$APP_DIR/recordings" "$APP_DIR/transcripts" /var/lib/asterisk/sounds/phone-agent
else
  echo "warning: asterisk user missing; keeping current ownership for runtime data"
fi

echo "== Reload services"
systemctl daemon-reload
systemctl enable --now phone-agent-dashboard.service phone-agent-health.timer
asterisk -rx "dialplan reload" || true
asterisk -rx "module reload res_pjsip.so" || true
systemctl restart phone-agent-dashboard.service

echo "== Healthcheck"
"$APP_DIR/scripts/healthcheck.sh"
for attempt in {1..20}; do
  if curl -fsS http://127.0.0.1:8088/healthz >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8088/healthz >/dev/null

echo "== Production audit"
"$APP_DIR/scripts/production_audit.sh"

echo "Deployment ok. Rollback: bash $BACKUP_DIR/rollback.sh"
