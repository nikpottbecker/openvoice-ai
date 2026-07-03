# OpenVoice AI v0.1.0 Initial Preview

This is the first public preview of OpenVoice AI.

OpenVoice AI is an early-stage self-hosted AI communication platform for phone, email, dashboard workflows, automations and AI providers.

## Included

- AI phone-agent baseline
- Asterisk integration examples
- FastAPI dashboard baseline
- Call recording support
- Live transcript and call history foundations
- Email draft and SMTP/IMAP foundations
- NVIDIA and OpenRouter provider configuration
- Local STT/TTS baseline with faster-whisper and Piper
- STT benchmark and local STT pipeline audit tooling
- Cloudflare Access protected dashboard pattern
- Docker Compose development baseline
- Proxmox Community Scripts draft files
- Open-source project files, security docs and contribution templates

## Important Status

This release is a preview / early alpha.

Known priorities before production-ready use:

- improve German telephone STT quality
- complete setup wizard
- harden install and update flow
- add more automated tests
- validate Proxmox helper scripts in a fresh LXC
- improve dashboard UX and health visibility

## Not Included

This release must not contain:

- real audio recordings
- real transcripts
- private phone numbers
- API keys
- SMTP/IMAP passwords
- SIP credentials
- Cloudflare tokens
- SQLite databases with real data
