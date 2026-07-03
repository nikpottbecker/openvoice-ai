# n8n Google Calendar

Importiere `n8n/phone-agent-google-calendar.workflow.json` in n8n.

Danach:

1. Google-Calendar-Credential im Google-Calendar-Node auswaehlen.
2. Webhook-URL kopieren.
3. Webhook-URL in `/opt/phone-agent/.env` als `N8N_WEBHOOK_URL` eintragen.
4. Workflow aktivieren.

Der Agent sendet Termine als JSON. Google-OAuth bleibt komplett in n8n.
