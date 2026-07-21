# OpenVoice AI v0.1.2 Initial Production Operations Preview

This is still a preview / early alpha release. It improves the gap between local development and the production LXC by adding deploy, audit and rollback tooling plus a more interactive dashboard.

## Highlights

- Interactive dashboard settings for runtime STT, recording and LLM configuration.
- TTS dashboard page with voice selection, fallback configuration and sample playback.
- Real dashboard APIs for system, Asterisk, SIP, live calls, call history, recordings and AI usage.
- Production audit script that captures current LXC state without publishing secrets.
- Production deploy script with backup, validation, service reload and healthcheck.
- Rollback script for restoring the previous Asterisk/app/systemd/config state.

## Important

Local tests passing does not prove production readiness. Real phone calls through FRITZBox, SIP, Asterisk and OpenVoice AI remain the required acceptance path.
