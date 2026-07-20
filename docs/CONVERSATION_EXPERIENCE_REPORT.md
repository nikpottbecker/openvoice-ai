# Conversation Experience Report

Stand: 2026-07-05

## Ziel

OpenVoice AI pausiert neue Features. Prioritaet ist ein natuerlicher, robuster Telefonfluss mit messbarer STT-Qualitaet.

## Geaenderte Qualitaetsgates

- `tests/test_conversation_experience.py` prueft 57 deterministische Gespraechsfaelle.
- Abgedeckt sind Terminstart, deutsche Namen, Datums-/Uhrzeitangaben, Themen, Telefonnummern und Bestaetigung.
- Der Test verhindert explizit Wiederholungen wie `Wie kann ich Ihnen helfen?` nach erkanntem Terminwunsch.

## Gefundene Fehler

1. Ein expliziter Satz wie `Ich moechte einen Termin` fuehrte zu einer unnoetigen Bestaetigungsfrage. Wenn der Anrufer direkt seinen Namen sagte, blieb der Agent im falschen Slot.
2. Der Startsatz `Ich moechte einen Termin` wurde faelschlich als Datum und Uhrzeit gespeichert. Danach verrutschten Name, Datum, Thema und Telefonnummer.
3. Das Wort `Rueckruf` im Themen-Slot konnte den bestehenden Terminflow verlassen und den Intent wechseln.

## Korrekturen

- Explizite Terminwuensche starten direkt den Terminflow.
- Slot-Eingaben haben Vorrang vor neuer Intent-Erkennung.
- Datum/Uhrzeit werden nur vorbefuellt, wenn echte Zeit- oder Datumssignale vorhanden sind.
- Datums-/Zeitparser erkennt Wochentage, `heute`, `morgen`, `uebermorgen`, `naechste Woche`, `vormittags`, `nachmittags` und einfache gesprochene Uhrzeiten.
- Telefonnummern erkennen einfache gesprochene Ziffern wie `null eins sieben sechs`.

## Verifikation

Lokal ausgefuehrt:

```text
python -m pytest -q
58 passed
```

```text
python -m py_compile scripts/stt_pipeline_audit.py src/phone_agent/agent.py src/phone_agent/stt.py src/phone_agent/agi_entrypoint.py
OK
```

## STT-Benchmark Status

Das Audit-Skript `scripts/stt_pipeline_audit.py` wurde erweitert, aber noch nicht auf neuen echten Live-Calls ausgefuehrt.

Neue Messpunkte:

- Original-WAV-Metriken: Sample-Rate, Dauer, Pegel, Silence Events, RMS, Peak, Clipping-Hinweis
- Vorverarbeitungsvarianten: aktuelle Pipeline, reine Normalisierung, weicher Telefonbandpass, weiche AGC, ohne loudnorm
- Whisper-Varianten: base, small, optional medium, optional large-v3, optional large-v3-turbo
- Parametervergleich: beam size, Initial Prompt, VAD aus
- Optionale Wortgenauigkeit per manueller Referenztranskription

Beispiel fuer echten Serverlauf:

```bash
cd /opt/phone-agent
PYTHONPATH=src python scripts/stt_pipeline_audit.py \
  --app-dir /opt/phone-agent \
  --include-medium \
  --include-large \
  --output /opt/phone-agent/stt_audits/latest-live-audit.json
```

Mit Referenztranskripten:

```bash
PYTHONPATH=src python scripts/stt_pipeline_audit.py \
  --app-dir /opt/phone-agent \
  --reference-json /opt/phone-agent/stt_audits/references.json \
  --include-medium \
  --include-large \
  --output /opt/phone-agent/stt_audits/latest-live-audit-with-wer.json
```

`references.json` Format:

```json
{
  "CALLID-01.wav": "exakt gehoerter Satz des Anrufers"
}
```

## Offener Blocker

Der Remotezugriff wurde nachtraeglich ueber Paramiko hergestellt. Neue echte Live-Benchmarks wurden auf Call `1783096110_0` ausgefuehrt.

## Iteration 2026-07-05

### Benchmark 1: Prep-Varianten und base/small

Quelle: echter Call `1783096110_0`, 5 Turns, 8 kHz Original-WAV.

Wichtige Messwerte:

| Variante | Modell | Beam | Avg. Runtime | Clipping | Ergebnis |
| --- | --- | ---: | ---: | ---: | --- |
| current | base | 1 | 3.197 s | ja | verworfen: prepared WAV clippt auf 0.0 dB |
| current | base | 3 | 3.250 s | ja | verworfen: prepared WAV clippt auf 0.0 dB |
| normalize_only | base | 3 | 3.176 s | nein | brauchbar, aber nicht klar besser |
| telephone_band_soft | base | 3 | 3.066 s | nein | brauchbar, aber nicht klar besser |
| telephone_agc_soft | base | 1 | 3.025 s | nein | schnell, aber einzelne Transkripte schlechter |
| current | small | 1 | 10.120 s | ja | verworfen: live zu langsam |
| normalize_only | small | 1 | 10.105 s | nein | verworfen: live zu langsam |

### Benchmark 2: Sichere Gain-Varianten

Quelle: gleicher echter Call, 5 Turns.

| Variante | Modell | Beam | Avg. Runtime | Clipping | Entscheidung |
| --- | --- | ---: | ---: | ---: | --- |
| current | base | 3 | 6.522 s | 5/5 | verworfen |
| current_tp2 | base | 3 | 6.857 s | 0/5 | brauchbar |
| current_tp2_gain12 | base | 3 | 6.225 s | 0/5 | uebernommen |
| current_tp2_gain14 | base | 3 | 6.798 s | 2/5 | verworfen |
| current_tp3_gain14 | base | 3 | 7.938 s | 2/5 | verworfen |

Uebernommene Audio-Pipeline:

```text
highpass=f=80,lowpass=f=3800,loudnorm=I=-18:LRA=8:TP=-2.0,volume=1.2
```

Verifikation auf echter WAV:

```text
RIFF WAVE, 16 bit, mono 16000 Hz
mean_volume: -16.9 dB
max_volume: -0.5 dB
```

### Benchmark 3: Whisper-Modellstart

Frischer Prozess im LXC:

| Modellpfad | Ladezeit |
| --- | ---: |
| `base` | 25.379 s |
| lokaler HF-Snapshot | 0.497 s |
| app-lokaler Snapshot `/opt/phone-agent/models/whisper/base` | 0.592 s |

Entscheidung:

- Lokale Snapshot-Aufloesung uebernommen.
- STT-Warmup beim Callstart beibehalten.
- Das Base-Modell wurde nach `/opt/phone-agent/models/whisper/base` kopiert, damit die Runtime nicht vom Root-Hugging-Face-Cache abhaengt.

### Benchmark 4: CPU Threads

Echte WAV `1783096110_0-01.wav`, base, lokaler Snapshot:

| Threads | Beam | Runtime | Text |
| ---: | ---: | ---: | --- |
| 1 | 3 | 10.354 s | `Hallo, ich will gerne morgen ein Telefonat sein wollen.` |
| 2 | 3 | 7.213 s | `Hallo, ich will gerne morgen ein Telefonat sein wollen.` |
| 3 | 3 | 8.010 s | `Hallo, ich will gerne morgen ein Telefonat sein wollen.` |
| 4 | 3 | 8.177 s | `Hallo, ich will gerne morgen ein Telefonat sein wollen.` |

Entscheidung:

- Keine Thread-Aenderung. Default/2 Threads ist auf diesem LXC am besten.

### Conversation-Fix

Echter Log-Befund:

- Bei schlechter STT wurde ein normaler Satz im Telefonnummer-Slot als Telefonnummer gespeichert.

Korrektur:

- Telefonnummer-Slot akzeptiert nur Ziffern oder einfache gesprochene Ziffern.
- Nach einem Fehlversuch wird erneut gefragt.
- Nach zwei Fehlversuchen greift die vorhandene Anti-Loop-Logik.

Server-Smoke-Test im LXC:

```text
server_conversation_smoke_ok
```

## Iteration 2026-07-05: Antwortlaenge / Playback

Piper wurde direkt im LXC auf Standardantworten gemessen.

| Antwort | Vorher | Nachher | Differenz |
| --- | ---: | ---: | ---: |
| Begruessung | 3.593 s | 3.546 s | -0.047 s |
| Datumsfrage | 4.231 s | 2.258 s | -1.973 s |
| Telefonnummerfrage | 3.639 s | 2.127 s | -1.512 s |
| Bestaetigung | 3.897 s | 2.885 s | -1.012 s |
| Abschluss | 2.757 s | 2.548 s | -0.209 s |
| Wiederholungsfrage | 3.511 s | 3.128 s | -0.383 s |

Uebernommen wurden nur inhaltlich gleichwertige kuerzere Antworten:

- `Danke. Wann soll der Termin sein?`
- `Unter welcher Nummer erreicht Nik Sie?`
- `Ich leite es an Nik weiter. Passt das so?`
- `Danke. Ich leite es an Nik weiter.`
- `Das habe ich nicht verstanden. Bitte nochmal kurz.`

Zusatzgate:

- Jede deterministische Terminflow-Antwort hat maximal eine Frage.

Verifikation:

```text
python -m pytest -q
61 passed
```

Testabhängigkeiten liegen in `requirements-dev.txt`; Produktionsabhängigkeiten bleiben in `requirements.txt`.

Server-Smoke-Test:

```text
server_short_reply_smoke_ok
```

## Iteration 2026-07-05: STT-Diagnosewerte

Whisper-Segmentmetriken wurden auf echten schlechten Turns geprueft.

Beispiele aus Call `1783096110_0`:

| Turn | Rohtranskript | avg_logprob | no_speech_prob | Bewertung |
| --- | --- | ---: | ---: | --- |
| 01 | `Hallo, ich will gerne morgen ein Telefonat sein wollen.` | -1.048 | 0.205 | brauchbarer Intent |
| 02 | `Die Liedsprotpecker.` | -1.521 | 0.342 | Name schlecht erkannt |
| 03 | `Ich bin einfach sprechen.` | -1.418 | 0.330 | Thema schlecht erkannt |
| 04 | `Und das Design ist sehr englisch.` | -1.223 | 0.095 | unklarer Slot |
| 05 | `Leopph.` | -1.076 | 0.215 | falscher kurzer Text trotz akzeptabler Metrik |

Entscheidung:

- Keine harte Confidence-Sperre uebernommen, weil `Leopph` trotz brauchbarer Metrik falsch ist.
- `avg_logprob`, `no_speech_prob`, `compression_ratio` und Segmentanzahl werden jetzt im echten AGI-Log ausgegeben.
- Dadurch kann der naechste Live-Call datenbasiert bewertet werden.

## Iteration 2026-07-05: 50 vollstaendige Simulationscalls

Ergaenzt wurde ein Regressionstest mit 50 kompletten Termin-Dialogen:

```text
Terminstart -> Name -> Datum/Uhrzeit -> Thema -> Telefonnummer -> Bestaetigung
```

Geprueft wird:

- Termin bleibt ueber alle Turns im State.
- Kein Rueckfall auf `Wie kann ich Ihnen helfen?`.
- Maximal eine Frage pro Antwort.
- Name, Thema und Telefonnummer bleiben erhalten.
- Der Slotflow endet sauber mit `confirmed=True`.

Zusaetzlich gibt es einen Test fuer vorgefuellte Themen wie `Termin fuer Fotoshooting bitte`; in diesem Fall wird die Themenfrage uebersprungen und direkt nach der Nummer gefragt.

## Iteration 2026-07-05: Log-Timing-Analyzer

Ergaenzt wurde:

```text
scripts/analyze_call_timings.py
```

Das Skript extrahiert pro echtem Call:

- Recording-Zeit
- Audio-Dauer
- STT / Preprocessing / Whisper
- LLM
- TTS
- Playback
- Gesamtzeit nach Aufnahme
- Rohtranskript
- lange Antworten

Baseline auf altem Live-Call `1783096110_0`:

| Metrik | Wert |
| --- | ---: |
| Avg STT | 5.513 s |
| Avg Playback | 3.242 s |
| Avg nach Aufnahme | 8.278 s |
| Max nach Aufnahme | 10.465 s |

Diese Baseline ist vor den neuesten Runtime-Optimierungen entstanden. Der naechste echte Live-Call muss gegen diese Werte verglichen werden.

## Iteration 2026-07-05: Logbasierte Conversation-Fixes

Aus alten Logs:

- `morgen frueh` wurde als ganze Satz-Zeit gespeichert.
- `Ja!` im Bestätigungsslot konnte als zu kurzes schlechtes Transkript behandelt werden.

Korrektur:

- `frueh`, `früh`, `morgens`, `vormittags`, `nachmittags`, `abends` werden als Tageszeit gespeichert.
- `Ja!`, `okay`, `passt`, `genau` usw. sind im Bestätigungsslot gueltig.

Verifikation:

```text
server_frueh_ja_smoke_ok
```

## Iteration 2026-07-05: Datum/Uhrzeit robuster

Der Terminparser wurde nachgeschaerft, weil typische deutsche Telefonformulierungen Datum und Uhrzeit vermischen koennen.

Neu abgesicherte Beispiele:

| Eingabe | Datum | Uhrzeit |
| --- | --- | --- |
| `am 12.7. um 14 Uhr` | `12.7` | `14:00` |
| `heute um 16 Uhr 30` | `heute` | `16:30` |
| `morgen frueh zu telefonieren` | `morgen` | `morgens` |
| `Freitag Vormittag` | `freitag` | `vormittags` |
| `naechsten Dienstag nachmittags` | `dienstag` | `nachmittags` |
| `am Montag gegen drei` | `montag` | `3:00` |
| `Donnerstag um elf` | `donnerstag` | `11:00` |

Verifikation:

```text
python -m pytest -q
72 passed
server_date_time_smoke_ok
```

## Iteration 2026-07-05: Deutsche Umlaute und Mojibake

Die interne Textnormalisierung wurde erweitert:

- `ä`, `ö`, `ü`, `ß` werden fuer Matching normalisiert.
- Mojibake wie `Ã¼bermorgen` wird vor dem Matching repariert.
- Rueckrufsignale mit Umlaut wie `zurückrufen` werden erkannt.
- Gesprochene Uhrzeiten wie `fünfzehn Uhr` werden als `15:00` gespeichert.

Neu abgesicherte Beispiele:

| Eingabe | Ergebnis |
| --- | --- |
| `übermorgen um fünfzehn Uhr` | `uebermorgen / 15:00` |
| `Ã¼bermorgen um fÃ¼nfzehn Uhr` | `uebermorgen / 15:00` |
| `nächsten Dienstag nachmittags` | `naechsten dienstag / nachmittags` |
| `Bitte zurückrufen` | `callback` |

Verifikation:

```text
python -m pytest -q
79 passed
server_umlaut_mojibake_callback_smoke_ok
```

## Iteration 2026-07-09: Alltagssprache im Slotflow

Der deterministische Terminflow wurde fuer typische Telefonantworten erweitert:

- Namen werden von Einleitungen bereinigt:
  - `ich heiße Tim Becker` -> `Tim Becker`
  - `mein Vorname ist Laura` -> `Laura`
  - `der Name ist Schmitz` -> `Schmitz`
- Gesprochene Nummern akzeptieren `zwo`.
- Umgangssprachliche Bestaetigungen wie `jo`, `jawohl`, `klar`, `stimmt` schliessen den Confirm-Slot ab.
- Unklare Bestaetigungen fragen genau einmal nach; beim zweiten Fehlversuch wird die Nachricht aufgenommen und weitergeleitet.

Verifikation:

```text
python -m pytest -q
88 passed
```

Deployment-Status:

- Lokaler Code ist verifiziert.
- LXC-Deployment konnte in dieser Runde nicht abgeschlossen werden, weil SSH ueber Tailscale lokal mit `WinError 10013` blockiert wurde.

## Iteration 2026-07-09: Negative Bestaetigung und Namensformulierungen

Weitere Alltagssprache-Faelle wurden abgesichert:

- `ich bin der Nik` -> `Nik`
- `ich bin die Lea` -> `Lea`
- `nein`, `nee`, `nö` im Bestaetigungsslot beenden den Slot ohne Schleife und werden als Notiz weitergeleitet.

Verifikation:

```text
python -m pytest -q
93 passed
```

Deployment-Status:

- Lokal verifiziert.
- LXC-Deployment weiterhin offen, weil SSH lokal mit `WinError 10013` blockiert.

## Iteration 2026-07-09: STT-Audit-Ranking statt Bauchgefuehl

Das STT-Audit wurde erweitert, damit die naechste Modellentscheidung aus echten Messwerten entsteht:

- aktive Runtime-Pipeline und Audit-`current` sind jetzt identisch
- WER und CER bei manuellem Referenztranskript
- Wort- und Zeichengenauigkeit
- Real-Time-Factor pro Modell/Prep-Variante
- RSS-Memory pro Lauf
- automatisches Ranking nach Qualitaet, sonst nur diagnostisch nach leeren Transkripten/Halluzination/Laufzeit

Verifikation:

```text
python -m pytest -q
96 passed
```

Ergebnis:

- Noch kein neues aktives Modell gewaehlt, weil kein neuer echter Live-Call und kein Referenztranskript verfuegbar sind.
- Naechster objektiver Schritt ist: echter Call -> manuelle Referenz pro WAV-Segment -> Audit mit `base`, `small`, `medium`, optional `large-v3-turbo`.

## Iteration 2026-07-09: Fuzzy-Intent auch nach LLM-Fallback

Der Schutzpfad nach einer generischen LLM-Antwort nutzt jetzt dieselbe deutsche/fuzzy Termin-Erkennung wie der harte Vorfilter.

Abgesicherter Fall:

```text
Nutzer: Ich haette gerne einen Thermin
LLM: Wie kann ich Ihnen helfen?
Agent: Gerne. Wie ist Ihr Name?
```

Verifikation:

```text
python -m pytest -q
97 passed
```

## Iteration 2026-07-09: LLM-Postprocess konsistent normalisiert

Der LLM-Nachbearbeiter normalisiert deutsche Umlaute/Mojibake jetzt vor Intent-Erkennung und behandelt `Wie kann ich Ihnen helfen?` bei bereits erkanntem Termin als generische Antwort.

Neu abgesichert:

- `Bitte zurueckrufen` -> `callback`
- `intent=appointment` + `Wie kann ich Ihnen helfen?` -> `Gerne. Wie ist Ihr Name?`

Verifikation:

```text
python -m pytest -q
99 passed
```

## Iteration 2026-07-09: Timing-Analyzer getestet

Der Log-Timing-Analyzer hat jetzt einen Regressionstest mit synthetischem Phone-Agent-Log.

Geprueft wird:

- `record`
- `recording_audio`
- `stt`
- `preprocessing`
- `whisper`
- `llm`
- `tts`
- `playback`
- `after_record_total`
- Rohtranskript

Verifikation:

```text
python -m pytest -q
100 passed
```

## Iteration 2026-07-09: Kurze Bestaetigungen im AGI-Filter

Gefundener Fehler:

- Der Agent akzeptierte `jo`, `klar`, `stimmt`, `nee`, aber `_bad_transcript()` konnte kurze Antworten vor dem Agenten verwerfen.

Korrektur:

- Der AGI-Filter normalisiert Deutsch/Mojibake.
- Im Confirm-Slot sind jetzt kurze natuerliche Antworten erlaubt:
  `ja`, `jo`, `jawohl`, `nein`, `nee`, `noe`, `passt`, `genau`, `richtig`, `okay`, `ok`, `klar`, `stimmt`.

Verifikation:

```text
python -m pytest -q
101 passed
```

## Iteration 2026-07-09: Kurze Slot-Antworten im AGI-Filter

Gefundener Fehler:

- `_bad_transcript()` haette kurze, aber gueltige Slot-Antworten wie `Nik`, `Foto` oder `Montag` verworfen, bevor der Agent sie verarbeiten kann.

Korrektur:

- In erwarteten Slots `name`, `topic`, `date_time`, `phone` sind kurze Antworten ab 3 Zeichen erlaubt.
- Fuellwoerter wie `aeh`/`hm` bleiben blockiert.

Verifikation:

```text
python -m pytest -q
102 passed
```

## Iteration 2026-07-09: Referenztemplate fuer echte STT-Benchmarks

Das STT-Audit kann jetzt vor dem Modellvergleich eine Referenzvorlage erzeugen:

```text
python scripts/stt_pipeline_audit.py --app-dir /opt/phone-agent --call-id <CALL_ID> --write-reference-template /opt/phone-agent/stt_audits/<CALL_ID>/references.json
```

Erzeugt wird:

- `references.json`: WAV-Dateiname -> manuell einzutragender Referenztext
- `references.metadata.json`: Dateigroesse, Dauer, Sample-Rate, Pegel-/Silence-Metriken soweit `ffmpeg` verfuegbar ist

Nutzen:

- Nach einem echten Live-Call kann sofort eine WER/CER-faehige Referenz erstellt werden.
- Ohne Referenz bleibt die Modellentscheidung bewusst diagnostisch, nicht final.

Verifikation:

```text
python -m pytest -q
103 passed
```

## Iteration 2026-07-09: Fuelllaute nicht als Slotwerte speichern

Gefundener Fehler:

- Nach der Lockerung fuer kurze Antworten konnten Fuelllaute wie `aehm`/`mhm` in erwarteten Slots zu leicht durchrutschen.
- Das haette im Live-Call dazu fuehren koennen, dass `aehm` als Name oder Thema gespeichert wird.

Korrektur:

- AGI-Filter blockiert normalisierte Fuelllaute:
  `aeh`, `ae`, `aehm`, `eh`, `ehm`, `hm`, `hmm`, `mhm`, `mm`.
- Agent-Slotbereinigung entfernt dieselben Fuelllaute auch bei Direktaufrufen/Simulationen.
- Kurze echte Slotwerte wie `Uwe`, `Nik`, `Foto`, `Montag` bleiben erlaubt.

Verifikation:

```text
python -m pytest -q
104 passed
```

## Iteration 2026-07-09: Ja/Nein im Termin-Erkennungsslot erlauben

Gefundener Fehler:

- Der AGI-Filter erlaubte kurze Antworten wie `ja`, `nein`, `stimmt` nur im finalen `confirmed`-Slot.
- Die vorgelagerte Frage `Ich habe verstanden, dass es um einen Termin gehen koennte. Stimmt das?` nutzt aber `appointment_confirm`.
- Dadurch konnte ein korrektes `ja` im Live-Call vor dem Agenten als schlechtes Transkript abgefangen werden.

Korrektur:

- Kurze Ja/Nein-/Bestaetigungsantworten sind jetzt auch im Slot `appointment_confirm` erlaubt.

Verifikation:

```text
python -m pytest -q
105 passed
```

## Iteration 2026-07-09: Verneinte Terminvermutung verlaesst den Termin-State

Gefundener Fehler:

- Bei `appointment_confirm` setzte der Code bei Verneinung kurz `intent=unknown`.
- Die Rueckgabe lief aber ueber `_slot_reply()`, wodurch wieder `intent=appointment` gesetzt wurde.
- Das konnte den Anrufer trotz `nein` im Terminflow festhalten.

Korrektur:

- Verneinung im Termin-Erkennungsslot gibt jetzt ein echtes `LLMResult(intent="unknown")` zurueck und leert `expected_slot`.

Verifikation:

```text
python -m pytest -q
106 passed
```

## Iteration 2026-07-09: Datum und Uhrzeit als Teilantworten

Gefundener Fehler:

- `Mittwoch` wurde als Datum und zugleich als Uhrzeit gespeichert.
- `15 Uhr` konnte nicht sauber als Uhrzeit ohne Datum weitergefuehrt werden.
- `Mittwoch um 10` und `uebermorgen um 9` wurden ohne ausgeschriebenes `Uhr` nach der Zahl nicht vollstaendig erkannt.

Korrektur:

- Datum und Uhrzeit werden getrennt gespeichert.
- Datum zuerst: `Mittwoch` -> `Danke. Um welche Uhrzeit?`
- Uhrzeit zuerst: `15 Uhr` -> `Danke. An welchem Tag?`
- Danach vervollstaendigt die naechste Teilantwort den Slot ohne vorhandene Werte zu ueberschreiben.

Verifikation:

```text
python -m pytest -q
111 passed
```

## Iteration 2026-07-09: Telefonnummer nicht zu frueh akzeptieren

Gefundener Fehler:

- Drei Ziffern wurden bereits als Telefonnummer akzeptiert.
- Das kann aus STT-Bruchstuecken oder Rueckfragen faelschlich eine bestaetigte Rueckrufnummer machen.

Korrektur:

- Der Phone-Slot verlangt jetzt mindestens 5 erkannte Ziffern.
- Vollstaendige gesprochene/deutsche Nummern bleiben gueltig.

Verifikation:

```text
python -m pytest -q
112 passed
```

## Iteration 2026-07-09: Unklare Datum/Uhrzeit-Antworten nicht sofort speichern

Gefundener Fehler:

- Antworten wie `weiss ich nicht` konnten beim ersten Versuch als Datum gespeichert werden.
- Das fuehrt zu falschen Terminnotizen und einem kuenstlichen Fortschritt im Slotflow.

Korrektur:

- Datum/Uhrzeit wird nur gespeichert, wenn ein echtes Datum, eine echte Uhrzeit oder eine Tageszeit erkannt wird.
- Erst beim zweiten Fehlversuch greift der bestehende Anti-Loop und speichert die Antwort als Notiz.

Verifikation:

```text
python -m pytest -q
114 passed
```

## Iteration 2026-07-09: Natuerliche deutsche Uhrzeiten

Ergaenzt wurden typische gesprochene Uhrzeiten:

- `Mittwoch um halb drei` -> `mittwoch / 2:30`
- `Freitag viertel nach drei` -> `freitag / 3:15`
- `Montag viertel vor vier` -> `montag / 3:45`

Wichtig:

- Diese Muster werden vor einfachen Wort-Uhrzeiten geprueft, damit `halb drei` nicht als `3:00` gespeichert wird.

Verifikation:

```text
python -m pytest -q
120 passed
```

## Iteration 2026-07-09: Gesprochene deutsche Datumsangaben

Ergaenzt wurden typische gesprochene Datumsformen:

- `zwoelfter siebter um 14 Uhr` -> `12.7 / 14:00`
- `fuenfzehnter Juli um zehn` -> `15.7 / 10:00`

Nutzen:

- Anrufer muessen Datumsangaben nicht als Ziffern nennen.
- Der Agent verliert im Terminflow weniger Kontext, wenn STT ausgeschriebene Woerter liefert.

Verifikation:

```text
python -m pytest -q
122 passed
```

## Iteration 2026-07-09: Numerische und regionale Uhrzeitvarianten

Ergaenzt wurden weitere Telefonformulierungen:

- `halb 3` -> `2:30`
- `viertel nach 3` -> `3:15`
- `viertel drei` -> `2:15`
- `dreiviertel drei` -> `2:45`

Nutzen:

- Der Agent erkennt nord-/ost-/sueddeutsche Umgangssprache besser.
- STT-Ausgaben mit Ziffern statt ausgeschriebenen Zahlen bleiben verwertbar.

Verifikation:

```text
python -m pytest -q
126 passed
```

## Iteration 2026-07-09: Dativformen bei gesprochenen Datumsangaben

Ergaenzt:

- `am zwoelften siebten um 14 Uhr` -> `12.7 / 14:00`
- `am fuenfzehnten Juli um zehn` -> `15.7 / 10:00`

Nutzen:

- Der Agent versteht natuerlichere deutsche Datumsformulierungen, nicht nur Nennformen wie `zwoelfter siebter`.

Verifikation:

```text
python -m pytest -q
128 passed
```

## Iteration 2026-07-09: Gesprochene Telefonnummern mit Zahlen 10-19

Ergaenzt:

- `zehn`, `elf`, `zwoelf`, `dreizehn`, ..., `neunzehn` werden im Phone-Slot in Ziffern umgewandelt.
- Beispiele:
  - `null eins sieben sechs fuenfzehn dreizehn`
  - `null eins fuenf sieben siebzehn elf`

Nutzen:

- STT gibt Telefonnummern haeufig als groessere Zahlwoerter aus, statt jede Ziffer einzeln.
- Der Phone-Slot bleibt dennoch restriktiv und verlangt mindestens 5 erkannte Ziffern.

Verifikation:

```text
python -m pytest -q
130 passed
```

## Iteration 2026-07-09: Gesprochene Plus-Vorwahl

Ergaenzt:

- `plus vier neun ...` wird im Phone-Slot als `+49...` erkannt.

Nutzen:

- Internationale/deutsche Mobilnummern bleiben verwertbar, wenn STT das Pluszeichen ausschreibt.

Verifikation:

```text
python -m pytest -q
131 passed
```

## Iteration 2026-07-20: Gesprochene E-Mail-Adressen

Ergaenzt:

- `punkt`, `dot` -> `.`
- `at`, `ät`, `klammeraffe` -> `@`
- `minus`, `bindestrich` -> `-`
- `unterstrich`, `underscore` -> `_`

Beispiele:

- `nik punkt pottbecker at gmail punkt com` -> `nik.pottbecker@gmail.com`
- `foto minus team klammeraffe beispiel punkt de` -> `foto-team@beispiel.de`

Nutzen:

- Wenn der Anrufer eine Zusammenfassung per E-Mail moechte, kann der bestehende externe Entwurfsflow die Adresse auch aus gesprochenem STT-Text extrahieren.

Verifikation:

```text
python -m pytest -q
135 passed
```

## Iteration 2026-07-20: E-Mail-Zustimmung robuster

Ergaenzt:

- Consent-Erkennung nutzt dieselbe Normalisierung wie gesprochene E-Mail-Adressen.
- Varianten wie `per e mail` und `Terminbestaetigung` werden sauber erkannt.

Verifikation:

```text
python -m pytest -q
136 passed
```

## Iteration 2026-07-20: Termin-Vermutungsfrage verkuerzt

Geaendert:

- Alt: `Ich habe verstanden, dass es um einen Termin gehen koennte. Stimmt das?`
- Neu: `Geht es um einen Termin?`

Messbarer Effekt:

- Gesprochener Text von 66 auf 25 Zeichen reduziert.
- Weniger TTS- und Playback-Dauer fuer uneindeutige Termin-Signale.

Verifikation:

```text
python -m pytest -q
137 passed
```

## Iteration 2026-07-20: Standard-Terminflow weiter verkuerzt

Geaendert:

- `Danke. Wann soll der Termin sein?` -> `Wann soll der Termin sein?`
- `Worum geht es bei dem Termin?` -> `Worum geht es?`
- `Unter welcher Nummer erreicht Nik Sie?` -> `Welche Telefonnummer?`
- `Ich leite es an Nik weiter. Passt das so?` -> `Passt das so?`
- Finale Bestaetigung -> `Danke. Ich leite weiter.`

Messbarer Effekt im Standardflow:

```text
24 Gerne. Wie ist Ihr Name?
26 Wann soll der Termin sein?
14 Worum geht es?
21 Welche Telefonnummer?
13 Passt das so?
24 Danke. Ich leite weiter.
```

Verifikation:

```text
python -m pytest -q
138 passed
```

## Iteration 2026-07-20: Abbruchwoerter verlassen aktive Slots

Ergaenzt:

- `abbrechen`, `abbruch`, `doch nicht`, `vergiss`, `vergessen`, `egal`, `lassen`, `stop`, `stopp`

Nutzen:

- Solche Antworten werden nicht mehr als Name, Thema, Datum oder Telefonnummer gespeichert.
- Der Agent verlaesst den Terminflow sauber und fragt neutral weiter.

Verifikation:

```text
python -m pytest -q
140 passed
```

## Iteration 2026-07-20: Datum/Uhrzeit-Korrekturen im Slot

Ergaenzt:

- `nicht Mittwoch, Donnerstag um 15 Uhr`
- `nicht Mittwoch sondern Freitag um 10`

Nutzen:

- Korrekturen ueberschreiben den bisherigen Datum/Uhrzeit-Slot sauber.
- Der Agent behandelt Korrekturen nicht als neues Thema oder unklare Antwort.

Verifikation:

```text
python -m pytest -q
142 passed
```

## Iteration 2026-07-20: Telefonnummer-Korrekturen im Slot

Ergaenzt:

- `nicht 12345 sondern 0176 12345678`
- `nicht die alte, plus vier neun eins fuenf sieben drei`

Nutzen:

- Korrigierte Telefonnummern werden direkt uebernommen.
- Alte/falsche Nummernteile landen nicht im gespeicherten Phone-Slot.

Verifikation:

```text
python -m pytest -q
144 passed
```

## Iteration 2026-07-20: Namenkorrekturen im Slot

Ergaenzt:

- `nicht Mueller sondern Schmidt` speichert nur `schmidt`.

Nutzen:

- Korrekturen werden nicht als voller Satz in `caller_name`/`appointment.name` gespeichert.

Verifikation:

```text
python -m pytest -q
145 passed
```

## Iteration 2026-07-20: Themenkorrekturen im Slot

Ergaenzt:

- `nicht Fotoshooting sondern Video` speichert nur `video`.
- `nicht livestream, presseanfrage` speichert nur `presseanfrage`.

Nutzen:

- Korrekturen werden nicht als volles Thema gespeichert.
- Der Terminflow bleibt im richtigen Slot und fragt direkt nach der Telefonnummer.

Verifikation:

```text
python -m pytest -q
147 passed
```

## Iteration 2026-07-20: Doch-Bestaetigungen

Ergaenzt:

- `doch`
- `nein doch`

Nutzen:

- Korrekturen im Confirm-Slot werden menschlicher verstanden.
- `doch nicht` bleibt als Abbruch/Korrektur erhalten, weil Abbruchtexte vor Bestaetigungen geprueft werden.

Verifikation:

```text
python -m pytest -q
149 passed
```

## Iteration 2026-07-20: Name-Slot verarbeitet eingebettete Termindetails

Ergaenzt:

- `Nik Pottbecker morgen um 15 Uhr Fotoshooting`
  - Name: `nik pottbecker`
  - Datum: `morgen`
  - Uhrzeit: `15:00`
  - Thema: `Fotoshooting`

Schutz:

- `morgen um 15 Uhr Fotoshooting` wird nicht als Name gespeichert, sondern fragt weiter nach dem Namen.

Nutzen:

- Wenn Anrufer nach der Namensfrage direkt mehrere Informationen nennen, spart der Agent Rueckfragen und bleibt im Slotflow korrekt.

Verifikation:

```text
python -m pytest -q
151 passed
```

## Iteration 2026-07-20: Date-Time-Slot uebernimmt eingebettetes Thema

Ergaenzt:

- `morgen um 15 Uhr Fotoshooting`
  - Datum: `morgen`
  - Uhrzeit: `15:00`
  - Thema: `Fotoshooting`

Nutzen:

- Wenn der Anrufer Datum/Uhrzeit und Thema in einer Antwort nennt, wird die Themenfrage uebersprungen.
- Das spart eine komplette Telefonrunde inklusive STT, LLM/State und TTS/Playback.

Verifikation:

```text
python -m pytest -q
152 passed
```

## Iteration 2026-07-20: Topic-Slot uebernimmt eingebettete Telefonnummer

Ergaenzt:

- `Fotoshooting 0176 12345678`
- `Video null eins sieben sechs fuenfzehn dreizehn`

Nutzen:

- Wenn Anrufer Thema und Telefonnummer in einer Antwort nennen, wird die Telefonnummerfrage uebersprungen.
- Das spart eine weitere komplette Telefonrunde.

Verifikation:

```text
python -m pytest -q
154 passed
```

## Iteration 2026-07-20: Hybrid-Flow-Round-Count-Benchmark

Ergaenzt:

- `scripts/benchmark_conversation_flows.py`
- lokale Messung fuer deterministische Hybrid-Flows:
  - DTMF-Termin komplett
  - komprimierter Hybrid-Termin
  - Rueckruf
  - Nachricht

Messwert:

```text
scenario_count=4
avg_inputs=3.0
max_inputs=5
all_completed=true
dtmf_appointment_full inputs=5
hybrid_appointment_compressed inputs=3
callback_confirm inputs=2
message inputs=2
```

Nutzen:

- Der komprimierte Hybrid-Terminflow spart gegenueber dem reinen DTMF-Terminflow 2 Eingaben.
- Jede gesparte Eingabe spart im echten Call mindestens eine moegliche Aufnahme/STT/TTS/Playback-Runde.

Verifikation:

```text
python -m pytest -q tests/test_benchmark_conversation_flows.py tests/test_hybrid_menu.py
23 passed
```
