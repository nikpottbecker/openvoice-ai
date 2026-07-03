# Architecture

OpenVoice AI is designed as a modular communication platform.

## Current Runtime

- Asterisk answers SIP calls.
- The AGI entrypoint records caller audio.
- STT transcribes German phone audio.
- The agent builds a short stateful response.
- The LLM provider returns a concise answer.
- Piper renders local TTS audio.
- The dashboard shows calls, logs, recordings and email state.

## Module Boundaries

- `phone_agent`: current working phone-agent implementation.
- `openvoice_ai.core`: future orchestration layer.
- `openvoice_ai.providers`: external services and provider registry.
- `openvoice_ai.stt`: speech-to-text providers.
- `openvoice_ai.tts`: text-to-speech providers.
- `openvoice_ai.llm`: model providers.
- `openvoice_ai.plugins`: future plugin SDK.

## Data Safety

Runtime data must stay outside source control:

- recordings
- transcripts
- logs
- SQLite databases
- `.env`
- provider credentials
