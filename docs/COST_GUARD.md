# OpenRouter Kosten-Schutz

Stand: 2026-07-03

## Live-Konfiguration

- Primary: `google/gemini-2.5-flash-lite`
- Gewuenschter Slug `google/gemini-2.0-flash-lite-001` wurde getestet, OpenRouter meldet aktuell `No endpoints found`.
- Fallback: `openrouter/free`
- `max_tokens=80`
- `temperature=0.25`
- `top_p=0.8`
- `stream=true`
- Maximal `10` LLM-Runden pro Call
- Nur rolling summary und letzte Nutzeraussage werden gesendet
- Token-Schaetzung wird pro Antwort geloggt

## Messung

Letzter Test:

- STT: ca. `2.8s`
- LLM: ca. `0.4s`
- TTS: ca. `1.0s`
- geschaetzte Tokens: ca. `124` input, `19` output

Bei grob 150 Input- und 30 Output-Tokens pro Antwort liegt ein einzelner Turn mit Flash-Lite im Bruchteil eines Cents. Das 5-Euro-Guthaben sollte bei kurzen Calls sehr lange reichen.
