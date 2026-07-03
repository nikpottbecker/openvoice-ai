# Proxmox Community Scripts Preparation

This project is being prepared for a future Community Scripts submission.

The current contribution guide requires new applications to be submitted to `ProxmoxVED`, not directly to the older `ProxmoxVE` script repository. A new container app needs:

- `ct/openvoice-ai.sh`
- `install/openvoice-ai-install.sh`
- matching metadata through the current website data workflow
- syntax checks
- ShellCheck
- real Proxmox testing through the CT script URL from a fork

Reference: [Community Scripts Contribution Guide](https://community-scripts.org/docs/contribution/guide).

## Planned Defaults

- App: `OpenVoice AI`
- Tags: `ai;communication;phone`
- OS: Debian 12
- CPU: 4
- RAM: 6144 MB
- Disk: 20 GB
- Unprivileged LXC: yes
- Dashboard port: 8088

## Validation Checklist

- `bash -n ct/openvoice-ai.sh`
- `bash -n install/openvoice-ai-install.sh`
- `shellcheck ct/openvoice-ai.sh install/openvoice-ai-install.sh`
- install through the forked raw GitHub CT script
- verify Asterisk service
- verify dashboard service
- verify no secrets in scripts
- verify update function preserves `.env` and runtime data
