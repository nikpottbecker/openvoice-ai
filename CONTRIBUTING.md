# Contributing

Thanks for helping make OpenVoice AI useful and safe.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install ruff mypy pytest
```

## Checks

```bash
python -m compileall -q src
ruff check src tests
pytest
```

For shell scripts:

```bash
bash -n scripts/install.sh
bash -n scripts/healthcheck.sh
shellcheck scripts/*.sh
```

## Secrets

Never commit:

- `.env`
- API keys
- SIP credentials
- SMTP/IMAP passwords
- Cloudflare tunnel tokens
- phone numbers from real calls
- recordings
- transcripts
- SQLite databases with real data

Use `.env.example` for placeholders only.

## Pull Requests

- Keep changes focused.
- Include tests or a manual verification note.
- Update documentation when behavior changes.
- Do not include private deployment artifacts.

## Community Scripts

Proxmox Community Scripts submissions should follow the current ProxmoxVED workflow with separate `ct/` and `install/` scripts, syntax checks, ShellCheck and real Proxmox testing. See `docs/COMMUNITY_SCRIPTS.md`.
