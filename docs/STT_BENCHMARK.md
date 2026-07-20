# STT Benchmark

Stand: 2026-07-03

Basis: anonymisierter echter Live-Call aus der lokalen Testumgebung.

## Hardware

- CPU: 2 Kerne
- RAM im LXC: 6 GB
- Device: CPU
- Compute: int8

## Ergebnisse nach RAM-Erhoehung

| Modell | Status | Durchschnitt | Max. RSS | Qualitaet |
| --- | --- | ---: | ---: | --- |
| Whisper base | ok | 6.785 s | 2718 MB | Schnellstes praktikables Modell, aber weiter fehlerhaft |
| Whisper small | ok | 17.393 s | 2901 MB | Nicht durchgehend besser als base |
| Whisper medium | ok | 76.006 s | 3771 MB | Teils besser, aber fuer Live-Calls zu langsam |
| Whisper large-v3-turbo | ok | 91.869 s | 3717 MB | Teils besser, aber fuer Live-Calls zu langsam |
| NVIDIA Parakeet | skipped | - | - | Nicht verfuegbar: kein Speech/Parakeet-Modell in NVIDIA /models, lokal kein NeMo/Torch |

## Rohbefund

Basis: anonymisierter echter Live-Call aus der lokalen Testumgebung.

- Turn 1: `large-v3-turbo` und `medium` am naechsten am Termin-Kontext.
- Turn 2: alle Modelle schlecht; `medium` halluziniert einen YouTube-artigen Satz.
- Turn 3: alle Modelle schlecht.
- Turn 4: `medium`/`large-v3-turbo` deutlich plausibler als `base`.
- Turn 5: alle erkennen `Ja`.

## Empfehlung

Aktiv bleibt `base`, weil nur `base` fuer Live-Antwortzeiten praktikabel ist. `medium` und `large-v3-turbo` verbessern einzelne Turns, brauchen aber 76-92 Sekunden pro kurzer Aufnahme und sind damit fuer Live-Telefonie nicht akzeptabel.

Eine 95-Prozent-Qualitaetsaussage ist ohne manuell vorliegende Referenztranskripte nicht seriös moeglich. Der Benchmark speichert deshalb pro echtem Call alle Rohtranskripte unter:

`/opt/phone-agent/stt_benchmarks/<call_id>.json`

## Erweiterung 2026-07-05

Zusaetzlich gibt es jetzt ein auditierbares Pipeline-Skript:

`scripts/stt_pipeline_audit.py`

Es vergleicht auf echten Call-WAVs:

- Audio-Metriken: Dauer, Sample-Rate, Pegel, Silence Events, RMS, Peak, Clipping-Hinweis
- Prep-Varianten: aktuelle Pipeline, reine Normalisierung, weicher Telefonbandpass, weiche AGC, ohne loudnorm
- Whisper-Varianten: `base`, `small`, optional `medium`, optional `large-v3`, optional `large-v3-turbo`
- Parameter: beam size, Initial Prompt, VAD aus
- optionale WER/Wortgenauigkeit ueber manuelle Referenztranskripte

Ohne manuelle Referenz bleibt die Bewertung eine Rohtranskript- und Laufzeitmessung. Fuer das Ziel `>=95 %` muss mindestens ein echter Live-Call manuell referenziert werden.

## Erweiterung 2026-07-20: PCM-Audioqualitaet

`scripts/stt_pipeline_audit.py` schreibt pro Original- und vorbereitetem WAV jetzt auch ffmpeg-unabhaengige PCM-Messwerte:

- `pcm_rms_dbfs`
- `pcm_peak_dbfs`
- `pcm_clipping_percent`
- `quality_flags`

Wichtige Flags:

- `digital_silence`
- `very_short_audio`
- `very_low_level`
- `very_hot_level`
- `possible_clipping`
- `unexpected_sample_rate`
- `not_mono`

Diese Werte sollen bei echten Live-Calls zuerst geprueft werden, bevor STT-Modelle bewertet werden.

Der AGI-Livepfad loggt dieselben leichten PCM-Kernwerte direkt nach jeder Aufnahme:

```text
audio_quality call_id=<id> turn=<n> sample_rate=8000 channels=1 duration=...
rms_dbfs=... peak_dbfs=... clipping_percent=... flags=...
```

`scripts/analyze_call_timings.py` liest diese Zeilen und fasst sie pro Call als
`audio_quality_flags` sowie pro Turn als `audio_quality` zusammen.
Zusaetzlich wird eine `diagnosis`-Liste erzeugt, zum Beispiel:

- `recording_contains_digital_silence_check_record_timing_or_rtp`
- `recording_too_short_check_min_record_or_barge_in`
- `recording_too_quiet_check_gain_or_normalization`
- `recording_too_hot_or_clipping_reduce_gain`
- `unexpected_audio_format_check_asterisk_recording_pipeline`
- `response_latency_above_5s_check_stt_llm_tts_breakdown`

## Erweiterung 2026-07-09

Das Audit-Skript bewertet Varianten jetzt strenger und reproduzierbarer:

- Die `current`-Prep-Variante entspricht der aktiven Runtime-Pipeline:
  `highpass=f=80,lowpass=f=3800,loudnorm=I=-18:LRA=8:TP=-2.0,volume=1.2`
- Pro Transkript werden `runtime_seconds`, `realtime_factor`, `rss_mb`, Rohtext und Auffaelligkeiten gespeichert.
- Wenn ein manuelles Referenztranskript uebergeben wird, werden `WER`, `CER`, Wortgenauigkeit und Zeichengenauigkeit berechnet.
- Die Zusammenfassung wird automatisch gerankt:
  - mit Referenz: Qualitaet vor Laufzeit
  - ohne Referenz: nur diagnostisch nach leeren Transkripten, Halluzinationsflags und Laufzeit

Beispiel:

```bash
python scripts/stt_pipeline_audit.py \
  --app-dir /opt/phone-agent \
  --call-id <CALL_ID> \
  --write-reference-template /opt/phone-agent/stt_audits/<CALL_ID>/references.json

python scripts/stt_pipeline_audit.py \
  --app-dir /opt/phone-agent \
  --call-id <CALL_ID> \
  --reference-json /opt/phone-agent/stt_audits/<CALL_ID>/references.json \
  --include-medium \
  --output /opt/phone-agent/stt_audits/<CALL_ID>/audit.json
```

Referenzformat:

```json
{
  "1783096110_0-0001.wav": "Ich moechte morgen um 15 Uhr einen Termin fuer ein Fotoshooting machen."
}
```

Neben `references.json` wird eine `references.metadata.json` mit WAV-Pfaden, Dateigroesse und Audio-Metriken geschrieben. Falls `ffmpeg` lokal fehlt, werden Basis-WAV-Metadaten trotzdem erzeugt; erweiterte Pegel-, Silence- und Clipping-Metriken kommen erst auf einem System mit `ffmpeg`.

Quellen fuer naechste Modellrunde:

- faster-whisper dokumentiert CPU-`int8`, Beam Size, VAD und lokale/CT2-Inferenz als geeignete Produktionsbasis.
- NVIDIA NeMo dokumentiert mehrsprachige ASR-Modelle mit Deutsch-Support; Canary/Parakeet bleiben Kandidaten fuer den naechsten echten LXC-Benchmark, sobald die Hardware erreichbar ist.
