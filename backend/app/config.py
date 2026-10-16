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

    # Demo exchange rates: units of currency per 1 EUR. Fixed on purpose; the real source is an open question.
    fx_rsd_per_eur: float = 117.0
    fx_usd_per_eur: float = 1.08
    # Default weights for supplier scoring (percent). Changeable per request in the UI.
    weight_price: int = 30
    weight_lead_time: int = 20
    weight_reliability: int = 20
    weight_terms: int = 15
    weight_external_risk: int = 15
    # Starting markup until analytics can recommend one (proposal). 0.15 = 15%.
    default_markup: float = 0.15
    # Upper limit for a single purchase order, EUR.
    po_budget_limit_eur: float = 50000

    # Incoming mail (IMAP). Credentials belong in .env only.
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    imap_ssl: bool = True

    @property
    def allowed_recipients(self) -> frozenset[str]:
        return frozenset(a.strip().lower() for a in self.mail_allowed_recipients.split(",") if a.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
