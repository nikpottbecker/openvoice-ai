# Community Scripts PR Draft

Do not submit this PR without final maintainer confirmation.

## Title

Add OpenVoice AI LXC helper script

## Description

OpenVoice AI is a self-hosted AI communication platform with phone agent, dashboard, STT/TTS, AI providers and automation support.

This contribution adds draft Proxmox LXC helper scripts for installing OpenVoice AI in a Debian container.

## Files

- `ct/openvoice-ai.sh`
- `install/openvoice-ai-install.sh`

## Notes

- The app is currently preview / early alpha.
- Users must configure runtime settings through the web setup or `.env`.
- No API keys, SIP credentials, SMTP passwords, recordings, transcripts or private data are included.

## User Configuration After Install

Users must provide:

- admin account
- STT provider/model settings
- TTS provider/model settings
- LLM provider keys
- SIP provider or FRITZ!Box credentials
- SMTP/IMAP credentials, if email is used
- Cloudflare Access/Tunnel settings, if exposed remotely
- n8n/Calendar credentials, if automation is used

## Local Validation

- Bash syntax check: required
- ShellCheck: required before PR
- Fresh Proxmox LXC install test: required before PR
- Update flow test: required before PR
- Secret scan: required before PR
