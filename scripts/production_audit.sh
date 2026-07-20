#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/phone-agent}"
OUT_DIR="${OUT_DIR:-$APP_DIR/production_audits/$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$OUT_DIR"

run_capture() {
  local name="$1"
  shift
  {
    echo "$ $*"
    "$@" 2>&1 || true
  } >"$OUT_DIR/$name.txt"
}

copy_if_exists() {
  local source="$1"
  local target="$2"
  if [[ -e "$source" ]]; then
    cp -a "$source" "$OUT_DIR/$target"
  fi
}

redact_file() {
  local source="$1"
  local target="$2"
  if [[ -f "$source" ]]; then
    sed -E \
      -e 's/(password[[:space:]]*=[[:space:]]*).*/\1***REDACTED***/Ig' \
      -e 's/(secret[[:space:]]*=[[:space:]]*).*/\1***REDACTED***/Ig' \
      -e 's/(token[[:space:]]*=[[:space:]]*).*/\1***REDACTED***/Ig' \
      -e 's/(api[_-]?key[[:space:]]*=[[:space:]]*).*/\1***REDACTED***/Ig' \
      -e 's/(OPENROUTER_API_KEY=).*/\1***REDACTED***/' \
      -e 's/(NVIDIA_API_KEY=).*/\1***REDACTED***/' \
      -e 's/(SMTP_PASSWORD=).*/\1***REDACTED***/' \
      -e 's/(IMAP_PASSWORD=).*/\1***REDACTED***/' \
      "$source" >"$OUT_DIR/$target"
  fi
}

{
  echo "# OpenVoice AI Production Audit"
  echo
  echo "- UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- APP_DIR: $APP_DIR"
  echo "- Host: $(hostname 2>/dev/null || echo unknown)"
} >"$OUT_DIR/SUMMARY.md"

if [[ -d "$APP_DIR/.git" ]]; then
  run_capture git-status git -C "$APP_DIR" status --short
  run_capture git-head git -C "$APP_DIR" rev-parse HEAD
  run_capture git-log git -C "$APP_DIR" log -5 --oneline --decorate
fi

run_capture system-uname uname -a
run_capture system-free free -h
run_capture system-disk df -h "$APP_DIR"
run_capture system-processes ps aux
run_capture services systemctl --no-pager --full status asterisk phone-agent-dashboard cloudflared phone-agent-health.timer
run_capture dashboard-health curl -fsS http://127.0.0.1:8088/healthz
run_capture dashboard-api-status curl -fsS http://127.0.0.1:8088/api/status
run_capture asterisk-version asterisk -rx "core show version"
run_capture asterisk-channels asterisk -rx "core show channels"
run_capture asterisk-registrations asterisk -rx "pjsip show registrations"
run_capture asterisk-endpoints asterisk -rx "pjsip show endpoints"
run_capture asterisk-dialplan asterisk -rx "dialplan show from-fritzbox"
run_capture asterisk-rtp asterisk -rx "rtp show settings"

copy_if_exists /etc/asterisk/extensions.conf asterisk-extensions.conf
redact_file /etc/asterisk/pjsip.conf asterisk-pjsip.redacted.conf
copy_if_exists /etc/systemd/system/phone-agent-dashboard.service phone-agent-dashboard.service
copy_if_exists /etc/systemd/system/phone-agent-health.service phone-agent-health.service
copy_if_exists /etc/systemd/system/phone-agent-health.timer phone-agent-health.timer
copy_if_exists "$APP_DIR/config/phone_menu.json" phone_menu.json
copy_if_exists "$APP_DIR/config/runtime_settings.json" runtime_settings.json
copy_if_exists "$APP_DIR/config/tts_settings.json" tts_settings.json
redact_file "$APP_DIR/.env" env.redacted

if [[ -d "$APP_DIR/logs" ]]; then
  mkdir -p "$OUT_DIR/logs"
  for log in "$APP_DIR"/logs/*.log; do
    [[ -f "$log" ]] || continue
    tail -n 500 "$log" >"$OUT_DIR/logs/$(basename "$log").tail"
  done
fi

if [[ -d "$APP_DIR/recordings" ]]; then
  find "$APP_DIR/recordings" -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' \
    | sort -r \
    | head -200 >"$OUT_DIR/recordings.latest.txt" || true
fi

if [[ -d "$APP_DIR/transcripts" ]]; then
  find "$APP_DIR/transcripts" -type f -name '*.json' -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' \
    | sort -r \
    | head -200 >"$OUT_DIR/transcripts.latest.txt" || true
fi

cat >>"$OUT_DIR/SUMMARY.md" <<EOF

## State Checklist

| Area | Implemented | Installed | Activated | Live Tested |
| --- | --- | --- | --- | --- |
| Asterisk dialplan | check repo/audit | check files | see asterisk-dialplan.txt | requires live call |
| PJSIP FRITZBox | check repo/audit | see redacted pjsip | see registrations | requires live call |
| Hybrid DTMF menu | check repo/audit | see phone_menu.json | see AGI logs | requires live DTMF |
| STT model | check runtime_settings | check Python env | see logs | requires live recording |
| TTS voice | check tts_settings | check model files | see logs | requires live phone audio |
| Dashboard | check repo/audit | see systemd | see dashboard-health.txt | see Cloudflare Access |

EOF

echo "Production audit written to $OUT_DIR"
