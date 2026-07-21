# OpenVoice AI v0.1.3 Production Deployment Hotfix

This release fixes issues found while publishing the dashboard to the production LXC.

## Fixes

- Deploy script no longer fails when scripts are already located in `/opt/phone-agent`.
- Deploy script no longer fails hard if the `asterisk` user is missing in a dashboard-only runtime.
- Dashboard startup no longer imports Python's removed `audioop` module on Python 3.13.

## Production Status

The production LXC can run the dashboard service on port `8088`; external access remains protected by Cloudflare Access.
