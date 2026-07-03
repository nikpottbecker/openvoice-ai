# OpenVoice AI Dashboard

## Lokal

- Service: `phone-agent-dashboard.service`
- Port: `8088`
- Healthcheck: `http://127.0.0.1:8088/healthz`
- Dashboard blockiert direkte Aufrufe ohne Cloudflare-Access-Header mit `403`.

## Cloudflare Tunnel

Der bestehende Tunnel laeuft auf dem Proxmox-Host als tokenbasierter `cloudflared`-Service.
Dieser Modus hat keine lokale `config.yml`; Public Hostnames werden in Cloudflare Zero Trust verwaltet.

Empfohlene Public-Hostname-Konfiguration:

- Public hostname: z. B. `dashboard.example.com`
- Service: `http://CONTAINER_IP:8088`
- Access Application: erforderlich
- Policy: nur erlaubte Benutzer/E-Mail-Adressen

Ohne Cloudflare Access bleibt das Dashboard unbenutzbar, weil die Anwendung den Header
`Cf-Access-Authenticated-User-Email` verlangt.

## Updates

```bash
cd /opt/phone-agent
git pull
/opt/phone-agent/.venv/bin/pip install -r requirements.txt
systemctl restart phone-agent-dashboard
```

Bei manueller Dateiuebertragung:

```bash
systemctl restart phone-agent-dashboard
systemctl status phone-agent-dashboard --no-pager
```
