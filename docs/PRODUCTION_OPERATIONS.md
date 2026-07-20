# OpenVoice AI Production Operations

Local implementation is not production proof. A feature counts as usable only after it is installed on the LXC, activated in Asterisk/OpenVoice AI, and verified through a real FRITZBox SIP call.

## Productive Deployment

Run on the production LXC as root:

```bash
cd /opt/phone-agent
git pull --ff-only origin main
sudo bash scripts/deploy_production.sh
```

The deploy script performs:

- backup of Asterisk, systemd units, app config, logs, transcripts and dashboard DB
- dependency update
- Python import/syntax validation
- runtime, menu and TTS config validation
- controlled service reload/restart
- healthcheck
- production audit

Rollback command is printed at the end of each deployment:

```bash
sudo bash /opt/phone-agent/backups/<timestamp>/rollback.sh
```

## Production Audit

Run any time on the LXC:

```bash
sudo bash /opt/phone-agent/scripts/production_audit.sh
```

Audit output is written to:

```text
/opt/phone-agent/production_audits/<timestamp>/
```

The audit redacts known secret fields and captures:

- current Git version and working tree
- system resources
- Asterisk dialplan, PJSIP registrations, endpoints, channels and RTP settings
- dashboard health/API status
- phone-agent logs
- latest recordings and transcripts
- active menu, runtime and TTS config

## Live Test Protocol

Before a test call:

```bash
sudo journalctl -u phone-agent-dashboard -f
sudo tail -f /opt/phone-agent/logs/phone-agent.log
sudo asterisk -rvvv
```

Run these real phone tests:

1. DTMF-only appointment: press `1`, choose a weekday, choose time, say a short topic, confirm with `1`.
2. Mixed flow: press `1`, say `Mittwoch nachmittags Fotoshooting`, confirm by key.
3. Name test: say `Nik` and `Nik Pottbecker`; do not accept fantasy names without confirmation.
4. Callback: press `4`, confirm caller number with `1`.
5. Message: press `5`, leave a short message.
6. Invalid key: press an unavailable key twice and confirm graceful fallback.
7. Timeout: provide no input and verify the menu/help path.
8. Barge-in: press a key during the greeting.

After each test:

```bash
sudo bash /opt/phone-agent/scripts/production_audit.sh
```

Inspect:

- `transcript_full`
- `audio_quality`
- `timing phase=record/stt/llm/tts/playback`
- `dtmf_detected`
- `hybrid_menu_action`
- saved WAV files in `/opt/phone-agent/recordings/<call_id>/`

## Completion Criteria

A dashboard, DTMF menu, STT model or TTS voice is only marked production-ready when:

- it appears in the production audit
- the live dialplan routes into the active AGI
- real call logs prove it was used
- recordings/transcripts were reviewed
- rollback exists for the deployed version
