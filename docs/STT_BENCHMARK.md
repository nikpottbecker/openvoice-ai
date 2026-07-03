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
