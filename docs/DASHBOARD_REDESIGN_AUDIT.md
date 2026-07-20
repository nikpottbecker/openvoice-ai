# OpenVoice AI Dashboard Redesign Audit

## Ziel

Das Dashboard wird als professionelles Operations-Produkt fuer eine selbst gehostete AI Communication Platform weiterentwickelt. Der Umbau bleibt bewusst auf die Web-Oberflaeche begrenzt: keine Aenderungen am Telefonagenten, keine neuen Integrationen, keine Secrets im UI.

## Externe Produktmuster

Als Orientierung dienen offizielle ElevenLabs-Dokumente zu ElevenAgents und Conversational AI:

- ElevenAgents positioniert Agents, Developer Tools sowie Monitoring und Evaluation als zusammenhaengenden Produktbereich.
- Das Analytics-Dashboard beschreibt granulare Echtzeitmetriken nach Agent, Zeit, Sprache, Call-Typ und Modell.
- Conversation Analysis und Success Evaluation zeigen, dass Gespraeche suchbar, auswertbar und qualitativ bewertbar sein sollten.
- Real-time Insights priorisiert Live-Aktivitaet, Trends und naechste Aktionen.
- Agent Testing betont reproduzierbare Multi-Turn-Konversationstests.

Quellen:

- https://elevenlabs.io/docs/eleven-agents/overview
- https://elevenlabs.io/docs/eleven-agents/dashboard
- https://elevenlabs.io/docs/eleven-agents/customization/agent-analysis
- https://elevenlabs.io/docs/eleven-agents/customization/agent-analysis/success-evaluation
- https://elevenlabs.io/docs/eleven-agents/dashboard/spotlight/real-time-insights
- https://elevenlabs.io/docs/eleven-agents/customization/agent-testing

## Vorheriger Zustand

- Sehr schlankes dunkles Layout mit einfacher Sidebar.
- Alle Kernrouten waren vorhanden, aber visuell gleichrangig und wenig produktartig.
- Tabellen, Logs und Audio waren funktional, aber nicht fuer schnelles Scannen optimiert.
- Keine globale Suche/Command-Palette.
- Responsives Verhalten war rudimentaer.

## Umgesetzte Phase 1

- Neue App-Shell mit gruppierter Sidebar: Betrieb, Agent, Kommunikation, System.
- Topbar mit geschuetztem Status, Nutzerhinweis und Command-Palette.
- Design Tokens fuer Light/Dark Mode, Oberflaechen, Linien, Statusfarben und Abstaende.
- Einheitliche Komponenten: Page Header, Metric Grid, Section Card, Badge, Tabellen-Wrapper, Empty State.
- Kernseiten modernisiert: Dashboard, Live Call, Gespraeche, Call Detail, Aufgaben, E-Mail, Telefonmenue, KI, Logs, Settings.
- E-Mail bleibt manuell und sicher: keine automatischen externen Kundenmails.

## Naechste sinnvolle Phasen

1. Live Call als echte Timeline mit Turn-Latenzen, Audioqualitaet und STT-Rohtranskript erweitern.
2. Analytics-Seite aus bestehenden Timing-Logs ableiten.
3. Health/System-Seite aus Healthcheck, systemd, Asterisk und Speicherstatus bauen.
4. Settings in read-only + Setup-Wizard trennen.
5. Accessibility-Check und visuelle Browser-Screenshots in die Tests aufnehmen.
