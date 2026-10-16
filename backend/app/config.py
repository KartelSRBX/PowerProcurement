from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from the environment (.env in development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://powerprocurement:change-me@localhost:5432/powerprocurement"

    ai_provider: Literal["mock", "anthropic"] = "mock"
    ai_model: str = "claude-sonnet-5-5"
    ai_max_tokens: int = 4096
    ai_confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    anthropic_api_key: str = ""

    # Real sending is off by default; with it off every message goes to Mailpit.
    mail_real_send_enabled: bool = False
    mail_allowed_recipients: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "procurement@demo.local"

    @property
    def allowed_recipients(self) -> frozenset[str]:
        return frozenset(a.strip().lower() for a in self.mail_allowed_recipients.split(",") if a.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
