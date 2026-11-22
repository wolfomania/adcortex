"""Runtime configuration, read from `NM_*` environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BrainBackend = Literal["mock", "replay", "tribe"]


class Settings(BaseSettings):
    """All settings have safe local defaults; Modal deployment overrides a few.

    LLM provider keys are not listed here: each provider reads its own
    standard variable (`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).
    """

    model_config = SettingsConfigDict(env_prefix="NM_", extra="ignore")

    runtime: Literal["local", "modal"] = "local"
    data_dir: Path = Path(".nm-data")
    frontend_dist: Path | None = None
    brain_backend: BrainBackend = "mock"
    replay_fixture: Path | None = None

    # GPU worker only (NM_BRAIN_BACKEND=tribe).
    tribe_checkpoint: str = "facebook/tribev2"
    whisperx_python: str = "/opt/whisperx/bin/python"
    whisper_model: str = "large-v3"
    models_dir: Path | None = None

    min_duration_s: float = Field(default=3.0, gt=0)
    max_duration_s: float = Field(default=180.0, gt=0)
    max_upload_mb: int = Field(default=500, gt=0)
    min_script_chars: int = 20
    max_script_chars: int = 3000

    scene_threshold: float = 12.0
    min_scene_s: float = 1.0

    llm_model: str | None = None
    llm_video_input: Literal["auto", "off"] = "auto"
    llm_timeout_s: float = 240.0
    llm_retries: int = 2

    password: SecretStr | None = None
    secret_key: SecretStr | None = None
    session_days: int = 30
    cors_origins: list[str] = Field(default_factory=list)

    modal_app: str = "neuromarketing"
    modal_data_volume: str = "nm-data"
    modal_progress_dict: str = "nm-progress"
    warmup_cooldown_s: float = 240.0

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def password_enabled(self) -> bool:
        return bool(self.password and self.password.get_secret_value())

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_model and self.llm_model.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
