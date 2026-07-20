# Deutsch-STT Tuning

Stand: 2026-07-03

## Aktive Konfiguration

- `WHISPER_LANGUAGE=de`
- `WHISPER_MODEL=base`
- `RECORD_SECONDS=8`
- `SILENCE_SECONDS=1.5`
- Auto-Detect ist deaktiviert.

## Audio-Vorverarbeitung

Vor faster-whisper wird jede Aufnahme per ffmpeg vorbereitet:

- Mono
- 16 kHz
- Highpass 80 Hz
- Lowpass 3800 Hz
- Lautheitsnormalisierung `loudnorm`
- moderater Gain ohne 0.0-dB-Clipping

Aktive Pipeline nach Live-Benchmark:

```text
highpass=f=80,lowpass=f=3800,loudnorm=I=-18:LRA=8:TP=-2.0,volume=1.2
```

## Fehlerlogik

- Vollstaendiges Transkript wird als `transcript_full` geloggt.
- Leere oder offensichtlich zu kurze Transkripte fuehren zu genau einer Nachfrage.
- Beim zweiten Fehlversuch wird eine Nachricht aufgenommen und der Call beendet.

## Messung

Simulation mit deutscher Terminanfrage:

- STT: ca. `5.181s`
- erkannter Text: `Guten Tag, ich moechte morgen um 14 Uhr einen Termin ...`
- Intent: `appointment`

Die Erkennungszeit ist hoeher als mit `tiny`, aber fuer Deutsch am Festnetz robuster.

## Live-Benchmark 2026-07-05

- `small` wurde verworfen: ca. 10s pro Turn auf 2 CPU-Kernen.
- `base` bleibt aktiv.
- App-lokaler Hugging-Face-Snapshot wird automatisch verwendet: Modellstart ca. 0.6s statt ca. 25s.
- Current-Pipeline mit `volume=1.8` wurde verworfen, weil vorbereitete WAVs clippten.

## Messregeln ab 2026-07-09

Modellwechsel nur noch nach echtem Live-Call und Referenztranskript:

1. Original-WAV behalten.
2. Referenztext pro WAV-Segment manuell erfassen.
3. `scripts/stt_pipeline_audit.py` mit `--reference-json` ausfuehren.
4. Entscheidung nach `avg_word_accuracy`, `avg_char_accuracy`, Halluzinationsflags, Real-Time-Factor und RAM.
5. Ohne Referenztranskript keine `>=95 %`-Aussage und kein dauerhafter Modellwechsel.
