# Code Quality Plan

OpenVoice AI is transitioning from a working private deployment to a maintainable open-source project. The first pass intentionally avoids disruptive rewrites.

## Current Baseline

- Python syntax compiles.
- Shell scripts pass Bash syntax checks.
- Configuration is loaded from `.env`.
- Runtime data is excluded from Git.
- Existing phone functionality remains isolated in `src/phone_agent/`.

## Planned Improvements

- Consolidate logging helpers across phone, dashboard and email modules.
- Add type hints to public functions.
- Add docstrings to provider interfaces and service boundaries.
- Replace deployment-specific wording with configurable profile data.
- Add tests for STT preprocessing, LLM fallback, email drafts and dashboard masking.
- Define stable provider interfaces under `src/openvoice_ai/`.

## Non-Goals For This Pass

- No large runtime refactor.
- No change to the live phone-agent call flow.
- No migration of production data.
