# Security Policy

## Supported Versions

OpenVoice AI is currently pre-1.0. Security fixes target the main development branch until stable release branches exist.

## Reporting a Vulnerability

Do not open a public issue for vulnerabilities that expose credentials, recordings, transcripts, phone numbers or dashboard access.

Use a private security advisory or contact the maintainers directly. Include:

- affected version or commit
- deployment type
- impact
- reproduction steps
- suggested fix, if available

## Security Baseline

- Secrets belong in `.env`, never in code.
- Dashboard access must be authenticated.
- Cloudflare Access or an equivalent identity layer is required for public dashboard exposure.
- SIP/RTP should remain private.
- Recordings and transcripts must not be published.
- Logs must not print API keys or passwords.
