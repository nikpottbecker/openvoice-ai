# Changelog

All notable changes to OpenVoice AI will be documented in this file.

## 0.1.2 - 2026-07-21

Preview patch release focused on making dashboard and production operations less local-only.

- Add interactive dashboard settings for STT, recording, LLM provider and runtime limits without exposing secrets.
- Add TTS configuration page with voice selection, fallback voice, sample generation and persisted settings.
- Add real dashboard status APIs for system metrics, Asterisk/SIP state, active channels, live calls, recordings and AI usage.
- Filter simulated/demo transcripts out of real call history.
- Add production audit, deploy and rollback scripts for LXC deployments with backups before service changes.
- Add production operations documentation and live-call verification protocol.

## 0.1.1 - 2026-07-20

Preview patch release focused on call quality, observability and dashboard polish.

- Add hybrid DTMF and speech phone menu flows for faster deterministic call handling.
- Improve German conversation state handling for appointments, callbacks, names, dates, times and confirmations.
- Add benchmark tooling and tests for real-call conversation flows, STT audio quality diagnostics and call timing analysis.
- Improve STT runtime behavior with German fixed-language transcription, empty-transcript small-model retry and real-call benchmark discovery for per-call recording directories.
- Add recording quality logging for duration, sample rate, channels, RMS, peak and clipping flags.
- Redesign the FastAPI dashboard shell with grouped navigation, responsive layout, command palette, modern cards and safer read-only operational views.
- Add dashboard render tests and broaden automated coverage for AGI, mail, LLM post-processing, hybrid menu and STT audit helpers.
- Keep the release in preview / early alpha status; real production quality still depends on live-call STT benchmarks with human reference transcripts.

## 0.1.0 - 2026-07-03

Initial preview / early alpha.

- Prepare project for open-source release as OpenVoice AI.
- Add phone agent, dashboard, call recording and email draft baseline.
- Add STT benchmark tooling for real phone calls.
- Add STT pipeline audit tooling for local real-call quality analysis.
- Add Cloudflare Access protected dashboard pattern.
- Add documentation, contribution files and security checklist.
- Add Proxmox Community Scripts draft files.
- Add Docker Compose development baseline.
- Add branding placeholders and release documentation.
