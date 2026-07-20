# OpenVoice AI v0.1.1 Preview Patch

OpenVoice AI `v0.1.1` is a preview / early alpha patch release focused on making the phone agent easier to test, monitor and operate.

## Highlights

- Hybrid DTMF + speech phone menu for faster deterministic call handling.
- More robust German appointment conversation flow.
- STT and audio-quality benchmark improvements for real phone-call recordings.
- Recording quality logs for duration, level, clipping and format diagnostics.
- Modernized FastAPI dashboard shell with grouped navigation, command palette and responsive operational views.
- Expanded automated tests across AGI, menu, dashboard rendering, STT audit, timing analysis, mail service and LLM post-processing.

## Validation

- `python -m pytest -q`
- Dashboard route render checks for all core pages.
- Secret scan over source, docs, tests, scripts, config, examples and Asterisk templates.

## Known Limits

- This is still preview / early alpha software.
- The STT quality target for production-grade German phone calls requires more real-call benchmarks with human reference transcripts.
- Public installer and Proxmox helper workflows should still be treated as technical-preview paths.
