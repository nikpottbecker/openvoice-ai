# Phase 3: FRITZ!Box SIP einrichten

Wenn die FRITZ!Box nicht remote erreichbar ist, diese Schritte lokal ausfuehren.

## Neue Rufnummer fuer Asterisk zuweisen

1. FRITZ!Box-Oberflaeche oeffnen.
2. `Telefonie` -> `Telefoniegeräte`.
3. `Neues Gerät einrichten`.
4. `Telefon` auswaehlen.
5. `LAN/WLAN (IP-Telefon)` auswaehlen.
6. Benutzername und Passwort vergeben.
7. Die ungenutzte Festnetznummer als eingehende Nummer zuweisen.
8. Keine anderen Rufnummern zuweisen, wenn der Agent nur diese Nummer annehmen soll.

## Werte fuer Asterisk notieren

- FRITZ!Box-IP, z. B. `192.168.178.1`
- SIP-Benutzername
- SIP-Passwort
- Zugewiesene Rufnummer
- Waehle die lokale Rufnummer, die fuer den Agenten vorgesehen ist.

Diese Werte in `/etc/asterisk/pjsip.conf` eintragen, basierend auf `/opt/phone-agent/asterisk/pjsip.conf.example`.

Alternativ direkt anwenden:

```bash
sudo /opt/phone-agent/scripts/apply_fritzbox_sip.sh SIP_USERNAME SIP_PASSWORD FRITZBOX_IP
```

## Asterisk neu laden

```bash
sudo asterisk -rx "core reload"
sudo asterisk -rx "pjsip show registrations"
sudo asterisk -rx "pjsip show endpoints"
```

## Wichtig

Keine SIP-Portweiterleitung in der FRITZ!Box einrichten. Die Verbindung bleibt im LAN.
