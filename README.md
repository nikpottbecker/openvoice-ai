# OpenVoice AI

[![CI](https://github.com/nikpottbecker/openvoice-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/nikpottbecker/openvoice-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-preview%20alpha-orange.svg)](CHANGELOG.md)

**The Open-Source AI Communication Platform.**

OpenVoice AI is a self-hosted communication platform that connects phone calls, email, calendars, automations, dashboards and AI providers in one modular system.

The current release focuses on a German AI phone agent with Asterisk, local speech-to-text, local text-to-speech, AI call summaries, email drafts and a protected web dashboard. The long-term goal is a privacy-first platform for phone, email, calendar, chat, WhatsApp, Discord, Home Assistant, n8n and other channels.

> Status: v0.1.0 preview / early alpha. The existing phone agent works in a tested local deployment, but public installation workflows are still being hardened.

## Logo

Branding drafts live in `branding/`. The initial logo is intentionally simple and SVG-based so it can be refined before the first public release.

## Features

- AI Phone Agent
- Dashboard
- Call Recording
- Live Call Monitor
- Live Transcript
- AI Call Summary
- Email Drafts
- SMTP and IMAP
- Google Calendar via n8n
- Cloudflare Tunnel
- Cloudflare Access
- SQLite storage
- NVIDIA and OpenRouter providers
- Multiple AI provider architecture
- Multiple STT provider architecture
- Multiple TTS provider architecture
- Self-hosted deployment

## Screenshots

Screenshots and OpenGraph assets will live in `images/`. Do not publish screenshots that contain real phone numbers, transcripts, recordings, API keys or private customer data.

## Architecture

```text
Phone / Email / Calendar / Automations
              |
              v
        OpenVoice Core
              |
   +----------+----------+
   |          |          |
  STT        LLM        TTS
   |          |          |
faster-   NVIDIA /    Piper
whisper   OpenRouter
```

The current Python package is `phone_agent`. Future modules are prepared under `src/openvoice_ai/` so the project can grow without breaking the working phone installation.

## Dashboard

The dashboard is built with FastAPI, Jinja2 and lightweight JavaScript. It is designed for:

- live status and SIP registration
- active calls and transcripts
- call history with audio playback
- AI timing and provider status
- email drafts and manual send actions
- settings visibility without exposing secrets

Never expose the dashboard directly to the internet. Use Cloudflare Tunnel plus Cloudflare Access or an equivalent authenticated reverse proxy.

## Installation

Supported targets:

- Debian 12+
- Ubuntu 22.04+
- Proxmox LXC
- Docker / Docker Compose

### Quick Start

```bash
git clone https://github.com/nikpottbecker/openvoice-ai.git
cd openvoice-ai
sudo bash install.sh
sudo cp .env.example .env
sudo nano .env
```

Then configure:

- Asterisk SIP account
- STT model
- Piper voice
- AI provider keys
- SMTP/IMAP credentials
- n8n webhook and Google Calendar workflow
- Cloudflare Access for dashboard access

## Docker

`docker-compose.yml` is included as an early development baseline. Telephony deployments still need host networking and Asterisk/SIP planning; for production phone use, Proxmox LXC or a dedicated Linux host is recommended.

## Proxmox

The project is being prepared for a Community Scripts submission. See `docs/COMMUNITY_SCRIPTS.md`.

Current tested shape:

- Debian LXC
- Asterisk inside the container
- dashboard on port `8088`
- recordings stored under `/opt/phone-agent/recordings`
- secrets loaded from `.env`

## Cloudflare

Use Cloudflare Tunnel for dashboard access and Cloudflare Access for authentication. SIP/RTP should stay on the private network and should not be proxied through Cloudflare.

## Asterisk

Example configs are in `asterisk/`. Copy examples into `/etc/asterisk/`, insert local SIP credentials, then reload Asterisk.

## NVIDIA

NVIDIA NIM is supported through an OpenAI-compatible API endpoint. Set `LLM_PROVIDER=nvidia`, `NVIDIA_BASE_URL` and `NVIDIA_API_KEY` in `.env`.

## OpenRouter

OpenRouter is supported as primary or fallback LLM provider. Set `OPENROUTER_API_KEY`, model names and token limits in `.env`.

## Email

SMTP and IMAP are configured through `.env`. Internal summaries can be sent automatically; external customer emails are draft-first and require manual approval in the dashboard.

## Roadmap

See `ROADMAP.md`.

## FAQ

**Can I use this without cloud AI?**  
STT and TTS can run locally. LLM support currently targets external OpenAI-compatible providers; fully local LLM support is planned.

**Can I expose SIP publicly?**  
Not recommended. Keep SIP/RTP private or behind a carefully secured VPN/network design.

**Does the dashboard show secrets?**  
No. Secrets must be masked and configured only through `.env`.

## Support

See `SUPPORT.md`.

## Funding

OpenVoice AI is MIT licensed and self-hosted first. See `docs/FUNDING.md`.

## License

MIT. See `LICENSE`.
