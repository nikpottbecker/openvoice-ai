# Latenz-Optimierung

Stand: 2026-07-03

## Aktive Live-Konfiguration

- Asterisk Debug: aus
- Test-Playback `hello-world`: entfernt
- `RECORD_SECONDS=7`
- `SILENCE_SECONDS=1`
- `WHISPER_MODEL=base`
- `OPENROUTER_MODEL=google/gemini-2.5-flash-lite`
- `OPENROUTER_FALLBACK_MODEL=openrouter/free`
- LLM `max_tokens=100`, `temperature=0.3`
- TTS-Cache aktiv unter `/opt/phone-agent/cache/tts`

## Messwerte aus Simulation

Mit `base`:

- STT: ca. `7.568s`
- LLM: ca. `0.850s` bei KI-Fehlerfallback
- TTS: ca. `2.892s`

Mit `tiny`:

- STT: ca. `4.126s`
- LLM: ca. `9.719s` bei wechselhafter OpenRouter-Free-Antwort
- TTS: ca. `1.888s`

## Entscheidung

`base` ist aktiv, weil deutsche Festnetzsprache wichtiger ist als die kuerzeste STT-Latenz.

Das alte Gemini-2.0-Flash-Lite-Ziel wurde getestet, liefert aktuell aber `No endpoints found`. Live nutzt deshalb Gemini 2.5 Flash Lite.

## Naechste Hebel

- Wenn OpenRouter-Free haeufig langsam oder rate-limited ist, ein schnelleres kostenloses Modell testen, sobald verfuegbar.
- Falls STT-Genauigkeit zu schlecht wird, zurueck auf `base`.
- Live-Saetze kurz halten, da Piper-Latenz direkt mit Textlaenge steigt.
