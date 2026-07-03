# Installation

## Debian / Ubuntu

```bash
git clone https://github.com/YOUR_ORG/openvoice-ai.git
cd openvoice-ai
sudo bash install.sh
sudo cp .env.example .env
sudo nano .env
```

Install a Piper voice, configure Asterisk and reload the service.

## Proxmox LXC

Recommended baseline:

- Debian 12
- 4 CPU cores
- 6 GB RAM for STT benchmarking
- 20 GB disk
- private SIP/RTP network access

After the container is created, run the Debian installation steps inside it.

## Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Docker is useful for dashboard and non-SIP development. Production telephony deployments need additional host networking and Asterisk planning.

## Cloudflare Access

Expose the dashboard only through Cloudflare Tunnel plus Cloudflare Access or an equivalent authenticated reverse proxy. Do not expose port `8088` publicly without authentication.
