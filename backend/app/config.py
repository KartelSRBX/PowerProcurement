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

    # Where the app keeps its own files (the key that encrypts secrets entered in the Settings tab).
    data_dir: str = "data"
    # Optional Fernet key for those secrets; if empty, one is generated in data_dir on first use.
    app_secret_key: str = ""

    # Real sending is off by default; with it off every message goes to Mailpit.
    mail_real_send_enabled: bool = False
    mail_allowed_recipients: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "procurement@demo.local"

    # Exchange rates: units of currency per 1 EUR. "manual" uses the two numbers below; "nbs" uses the
    # National Bank of Serbia middle rates fetched from fx_nbs_url ({code} is replaced by EUR or USD).
    fx_source: Literal["manual", "nbs"] = "manual"
    fx_rsd_per_eur: float = 117.0
    fx_usd_per_eur: float = 1.08
    fx_nbs_url: str = "https://kurs.resenje.org/api/v1/currencies/{code}/rates/today"
    # Default weights for supplier scoring (percent). Changeable per request in the UI.
    weight_price: int = 30
    weight_lead_time: int = 20
    weight_reliability: int = 20
    weight_terms: int = 15
    weight_external_risk: int = 15
    # Starting markup until analytics can recommend one (proposal). 0.15 = 15%.
    default_markup: float = 0.15
    # A supplier that has not answered a sent letter after this many days gets a follow-up draft.
    followup_after_days: int = 3
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
def env_settings() -> Settings:
    """Settings from the environment only."""
    return Settings()


# Values a person saved in the Settings tab; they win over the environment. Kept in this process
# (the app runs as one process) and rebuilt from the database on start and after every save.
_overrides: dict = {}


def set_overrides(values: dict) -> None:
    _overrides.clear()
    _overrides.update(values)


def get_settings() -> Settings:
    base = env_settings()
    return base.model_copy(update=_overrides) if _overrides else base
