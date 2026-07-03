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
- Highpass 120 Hz
- Lowpass 3600 Hz
- leichte Rauschunterdrueckung `afftdn`
- Lautheitsnormalisierung `loudnorm`

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
