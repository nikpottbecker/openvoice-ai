#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/phone-agent}"
BACKUP_DIR="${1:-}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the production LXC."
  exit 1
fi

if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "Usage: sudo bash scripts/rollback_production.sh /opt/phone-agent/backups/<timestamp>"
  exit 1
fi

echo "== Rollback from $BACKUP_DIR"

if [[ -f "$BACKUP_DIR/asterisk.tgz" ]]; then
  tar -C / -xzf "$BACKUP_DIR/asterisk.tgz"
fi

if [[ -f "$BACKUP_DIR/systemd-phone-agent.tgz" ]]; then
  tar -C / -xzf "$BACKUP_DIR/systemd-phone-agent.tgz"
fi

if [[ -f "$BACKUP_DIR/config-and-data.tgz" ]]; then
  tar -C "$APP_DIR" -xzf "$BACKUP_DIR/config-and-data.tgz"
fi

if [[ -f "$BACKUP_DIR/git-head.txt" && -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" checkout --detach "$(cat "$BACKUP_DIR/git-head.txt")"
fi

systemctl daemon-reload
systemctl restart asterisk || true
systemctl restart phone-agent-dashboard.service || true
"$APP_DIR/scripts/healthcheck.sh" || true

echo "Rollback finished."
