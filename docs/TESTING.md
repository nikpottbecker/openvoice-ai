# Tests

## Lokaler Softwaretest

```bash
cd /opt/phone-agent
sudo scripts/healthcheck.sh
```

## Vollstaendige Simulation ohne Telefonanruf

```bash
cd /opt/phone-agent
sudo scripts/simulate_call.sh --text "Hallo, ich bin Example Caller und moechte morgen um 14 Uhr einen Termin wegen einer Projektbesprechung vereinbaren."
```

Der Test erzeugt:

- synthetische Anrufer-Audioeingabe
- STT-Transkript
- OpenRouter-Antwort mit Fallback
- Piper-Antwortdatei
- JSON-Statusdatei unter `/opt/phone-agent/transcripts/`

## Asterisk-Konfiguration pruefen

```bash
sudo asterisk -rx "dialplan show from-fritzbox"
sudo asterisk -rx "pjsip show registrations"
sudo asterisk -rx "pjsip show contacts"
```

## Testanruf

1. Unbenutzte Festnetznummer anrufen.
2. Der Agent sollte begruessen.
3. Beispiel sagen:

```text
Ich bin Example Caller und moechte am Freitag um 14 Uhr einen Termin wegen einer Projektbesprechung.
```

4. Pruefen:

```bash
ls -lah /opt/phone-agent/recordings
ls -lah /opt/phone-agent/transcripts
tail -n 100 /opt/phone-agent/logs/phone-agent.log
```

## n8n Webhook testen

```bash
curl -X POST "$N8N_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d @config/n8n-calendar-payload.example.json
```

## Erwartete offene Punkte beim ersten Test

- OpenRouter-Key muss gesetzt sein.
- Piper muss mit `sudo bash /opt/phone-agent/scripts/install_piper.sh` installiert sein.
- n8n muss Google Calendar OAuth eingerichtet haben.
- FRITZ!Box-SIP-Zugangsdaten muessen stimmen.
