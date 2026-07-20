#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte als root ausfuehren: sudo bash scripts/install.sh"
  exit 1
fi

APP_DIR="/opt/phone-agent"
PYTHON_BIN="${PYTHON_BIN:-python3}"

apt-get update
apt-get install -y --no-install-recommends \
  asterisk \
  curl \
  ffmpeg \
  git \
  jq \
  python3 \
  python3-venv \
  python3-pip \
  rsync \
  sox \
  unzip \
  ca-certificates

mkdir -p "$APP_DIR"/{logs,recordings,transcripts,config,models/piper}
mkdir -p "$APP_DIR/agi-bin"
mkdir -p /var/lib/asterisk/sounds/phone-agent

if [[ "$PWD" != "$APP_DIR" ]]; then
  rsync -a --delete --exclude ".venv" --exclude ".env" ./ "$APP_DIR"/
fi

cd "$APP_DIR"
"$PYTHON_BIN" -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt

cp -n .env.example .env
cp -n config/agent.system.prompt "$APP_DIR/config/agent.system.prompt"
cp -n config/phone_menu.example.json "$APP_DIR/config/phone_menu.json"

install -m 0755 scripts/healthcheck.sh "$APP_DIR/scripts/healthcheck.sh"
install -m 0755 scripts/install_piper.sh "$APP_DIR/scripts/install_piper.sh"
install -m 0755 scripts/simulate_call.sh "$APP_DIR/scripts/simulate_call.sh"
install -m 0755 scripts/update.sh "$APP_DIR/scripts/update.sh"
cat > "$APP_DIR/agi-bin/phone-agent-agi" <<'EOF'
#!/usr/bin/env bash
cd /opt/phone-agent
export PYTHONPATH=/opt/phone-agent/src
exec /opt/phone-agent/.venv/bin/python -m phone_agent.agi_entrypoint
EOF
chmod 0755 "$APP_DIR/agi-bin/phone-agent-agi"
install -m 0644 systemd/phone-agent-health.service /etc/systemd/system/phone-agent-health.service

chown -R asterisk:asterisk "$APP_DIR"/logs "$APP_DIR"/recordings "$APP_DIR"/transcripts "$APP_DIR/agi-bin" /var/lib/asterisk/sounds/phone-agent
chmod 0640 "$APP_DIR/.env"

systemctl daemon-reload
systemctl enable asterisk
systemctl restart asterisk

echo "Installation fertig. Danach .env, Piper, /etc/asterisk/pjsip.conf und FRITZ!Box einrichten."
echo "Piper installieren: sudo bash /opt/phone-agent/scripts/install_piper.sh"
