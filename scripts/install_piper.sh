#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/phone-agent"
MODEL_DIR="$APP_DIR/models/piper"
PIPER_DIR="$APP_DIR/vendor/piper"

mkdir -p "$MODEL_DIR" "$PIPER_DIR"
apt-get install -y --no-install-recommends libespeak-ng1 >/dev/null 2>&1 || true

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ASSET_PATTERN='linux_x86_64.tar.gz' ;;
  aarch64|arm64) ASSET_PATTERN='linux_aarch64.tar.gz' ;;
  *) echo "Nicht unterstuetzte Architektur: $ARCH"; exit 1 ;;
esac

URL="$(curl -fsSL https://api.github.com/repos/rhasspy/piper/releases/latest \
  | jq -r --arg pattern "$ASSET_PATTERN" '.assets[] | select(.name | contains($pattern)) | .browser_download_url' \
  | head -n 1)"

if [[ -z "$URL" || "$URL" == "null" ]]; then
  echo "Konnte Piper-Release nicht finden."
  exit 1
fi

tmp="$(mktemp -d)"
curl -fL "$URL" -o "$tmp/piper.tar.gz"
tar -xzf "$tmp/piper.tar.gz" -C "$tmp"
found_bin="$(find "$tmp" -type f -name piper | head -n 1)"
install -m 0755 "$found_bin" /usr/local/bin/piper
find "$tmp" -type f \( -name "*.so" -o -name "*.so.*" \) -exec install -m 0644 {} /usr/local/lib/ \;
ldconfig

if [ ! -e /usr/share/espeak-ng-data ] && [ -d /usr/lib/x86_64-linux-gnu/espeak-ng-data ]; then
  ln -s /usr/lib/x86_64-linux-gnu/espeak-ng-data /usr/share/espeak-ng-data
fi

MODEL_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium"
curl -fL "$MODEL_BASE/de_DE-thorsten-medium.onnx" -o "$MODEL_DIR/de_DE-thorsten-medium.onnx"
curl -fL "$MODEL_BASE/de_DE-thorsten-medium.onnx.json" -o "$MODEL_DIR/de_DE-thorsten-medium.onnx.json"

chown -R asterisk:asterisk "$MODEL_DIR" || true
rm -rf "$tmp"
echo "Piper installiert."
