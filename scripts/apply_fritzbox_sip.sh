#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 SIP_USERNAME SIP_PASSWORD [FRITZBOX_IP]"
  exit 2
fi

SIP_USERNAME="$1"
SIP_PASSWORD="$2"
FRITZBOX_IP="${3:-192.168.178.1}"

install -m 0600 /dev/null /etc/asterisk/pjsip.conf
sed \
  -e "s|FRITZBOX_IP|$FRITZBOX_IP|g" \
  -e "s|SIP_USERNAME|$SIP_USERNAME|g" \
  -e "s|SIP_PASSWORD|$SIP_PASSWORD|g" \
  /opt/phone-agent/asterisk/pjsip.conf.example > /etc/asterisk/pjsip.conf

asterisk -s /run/asterisk/asterisk.ctl -rx "core reload"
asterisk -s /run/asterisk/asterisk.ctl -rx "pjsip show registrations"
