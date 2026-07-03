from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "production"
    app_base_dir: Path = Path("/opt/phone-agent")

    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.0-flash-lite-001"
    openrouter_fallback_model: str = "openrouter/free"
    openrouter_max_tokens: int = Field(default=80, ge=1, le=80)
    openrouter_temperature: float = 0.25
    openrouter_top_p: float = 0.8
    openrouter_stream: bool = True
    openrouter_http_referer: str = "https://openvoice-ai.local"
    openrouter_app_title: str = "OpenVoice AI"
    llm_provider: str = "nvidia"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.2-3b-instruct"

    n8n_webhook_url: str = ""
    n8n_webhook_token: str = ""

    mail_from: str = ""
    mail_from_name: str = "OpenVoice AI"
    internal_summary_to: str = ""
    dashboard_public_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""

    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "de"

    piper_bin: Path = Path("/usr/local/bin/piper")
    piper_model: Path = Path("/opt/phone-agent/models/piper/de_DE-thorsten-medium.onnx")
    piper_config: Path = Path("/opt/phone-agent/models/piper/de_DE-thorsten-medium.onnx.json")

    asterisk_sounds_dir: Path = Path("/var/lib/asterisk/sounds/phone-agent")
    max_turns: int = Field(default=8, ge=1, le=20)
    max_llm_rounds_per_call: int = Field(default=10, ge=1, le=10)
    record_seconds: int = Field(default=7, ge=3, le=120)
    silence_seconds: float = Field(default=1.4, ge=0.5, le=10)
    min_record_seconds: float = Field(default=1.4, ge=0.0, le=10)
    post_playback_wait_seconds: float = Field(default=0.4, ge=0.0, le=3)

    @property
    def recordings_dir(self) -> Path:
        return self.app_base_dir / "recordings"

    @property
    def transcripts_dir(self) -> Path:
        return self.app_base_dir / "transcripts"

    @property
    def logs_dir(self) -> Path:
        return self.app_base_dir / "logs"

    @property
    def config_dir(self) -> Path:
        return self.app_base_dir / "config"


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    settings = Settings()
    for directory in (
        settings.recordings_dir,
        settings.transcripts_dir,
        settings.logs_dir,
        settings.config_dir,
        settings.asterisk_sounds_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return settings
