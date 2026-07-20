# TTS Voice Optimization

## Aktueller Runtime-Stand

- Provider: Piper lokal
- Aktive Stimme: `de_DE-thorsten-medium`
- Fallback: `de_DE-thorsten-medium`
- Sprache/Locale: Deutsch `de_DE`
- Piper-native Ausgabe: modellabhaengig, typischerweise 16 kHz oder 22.05 kHz PCM WAV
- Asterisk-Ausgabe: 8 kHz, mono, `pcm_s16le`
- Konvertierung: bevorzugt ffmpeg mit `soxr` Resampling und Loudness-Normalisierung
- Lokaler Fallback ohne ffmpeg: Python PCM-Resampling, nur fuer Entwicklungs-/Vergleichsumgebungen

## Warum noch keine neue Standardstimme gesetzt wurde

Die technische Messung kann Dateiformat, Pegel, Clipping, Laufzeit und Telefon-WAV-Eignung pruefen. Sie kann aber nicht sicher bewerten, ob eine Stimme im echten Anruf natuerlich, angenehm und professionell klingt. Deshalb bleibt die bisherige Stimme produktiv, bis mindestens drei echte Telefonate den neuen Kandidaten bestaetigen.

## Vergleichsskript

```bash
PYTHONPATH=/opt/phone-agent/src \
python /opt/phone-agent/scripts/benchmark_tts_voices.py \
  --app-dir /opt/phone-agent \
  --download-missing \
  --voices \
    de_DE-thorsten-medium \
    de_DE-thorsten-high \
    de_DE-thorsten_emotional-medium \
    de_DE-mls-medium \
    de_DE-kerstin-low \
    de_DE-ramona-low
```

Ausgabe:

`/opt/phone-agent/tts_voice_comparison/<timestamp>/`

Pro Stimme entstehen fuer alle sieben Testtexte:

- native Piper-WAV
- Asterisk-8-kHz-WAV
- Generierungszeit
- Dateigroesse
- Sample-Rate
- RMS/Peak/Clipping
- technische Flags

## Lokaler Entwicklungs-Benchmark vom 2026-07-20

Pfad:

`tts_voice_comparison/local-run/samples/`

Getestete Stimmen:

- `de_DE-thorsten-medium`
- `de_DE-thorsten-high`
- `de_DE-thorsten_emotional-medium`
- `de_DE-mls-medium`
- `de_DE-kerstin-low`
- `de_DE-ramona-low`

Technische Shortlist:

- `de_DE-ramona-low`: schnellster technisch sauberer Kandidat im lokalen Lauf
- `de_DE-kerstin-low`: ebenfalls technisch sauber, moeglicher natuerlicherer Kandidat
- `de_DE-thorsten-high`: hoehere Qualitaet, aber langsamer

Einschraenkung:

Der lokale Windows-Lauf hatte kein ffmpeg. Die 8-kHz-Dateien wurden deshalb mit dem Python-Fallback erzeugt. Der entscheidende Test muss auf dem LXC mit ffmpeg/Asterisk erfolgen.

## Dashboard

Die Seite `/tts` erlaubt:

- Provider anzeigen/auswaehlen
- Stimme auswaehlen
- Fallback-Stimme auswaehlen
- Sprachprobe erzeugen
- Geschwindigkeit ueber `length_scale` setzen
- Pausen ueber `sentence_silence` setzen
- Lautstaerke ueber `volume` setzen
- Standardkonfiguration speichern

API-Schluessel werden dort nicht angezeigt.

## Live-Test-Checkliste

Vor dem Umschalten der Standardstimme:

1. Begruessung und Hauptmenue anrufen.
2. Terminablauf durchspielen.
3. Rueckruf oder Nachricht durchspielen.

Bewerten:

- Natuerlichkeit
- Verstaendlichkeit ueber Festnetz
- Lautstaerke
- Pausen
- Aussprache von Namen, Zahlen, Uhrzeiten und Daten
- Reaktionszeit
- Artefakte nach Asterisk-Konvertierung

Erst wenn eine neue Stimme in diesen echten Telefonaten eindeutig besser klingt, `voice` in `/tts` speichern und `de_DE-thorsten-medium` als Fallback behalten.
