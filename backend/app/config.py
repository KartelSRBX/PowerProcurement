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
    # Delivery history as a scoring criterion: weight in percent (0 = off) and the number of delivered
    # orders with a promised date a supplier needs before its record counts. Set in Settings.
    weight_delivery_history: int = Field(default=0, ge=0, le=100)
    delivery_history_min_orders: int = Field(default=3, ge=2, le=50)
    # Starting markup until analytics can recommend one (proposal). 0.15 = 15%.
    default_markup: float = 0.15
    # A supplier that has not answered a sent letter after this many days gets a follow-up draft.
    followup_after_days: int = 3
    # A customs tariff whose rate date is older than this many days is flagged in calculations.
    duty_rate_max_age_days: int = Field(default=365, ge=30, le=3650)
    # How far a supplier invoice may differ from the order (percent of the order total or of a unit price)
    # before it is shown as differing. Set in Settings.
    invoice_tolerance_pct: float = Field(default=1.0, ge=0, le=20)
    # Article signals: a unit price at least this many percent above the last paid or ordered one, or a lead
    # time at least this many days and percent longer than the last order, is flagged. Set in Settings.
    signal_price_rise_pct: float = Field(default=10.0, ge=0, le=500)
    signal_lead_rise_pct: float = Field(default=25.0, ge=0, le=1000)
    signal_lead_rise_days: int = Field(default=3, ge=0, le=365)
    # Supplier re-checks: how many months a sanctions screening or a beneficiary confirmation stays
    # current, and how many days ahead the list shows what is coming due. Set in Settings.
    recheck_months: int = Field(default=12, ge=1, le=60)
    recheck_warn_days: int = Field(default=30, ge=0, le=365)
    # Request urgency: a request whose reply-by date is this many days away or fewer is shown as coming up.
    urgency_warn_days: int = Field(default=2, ge=0, le=30)
    # Daily summary: days without an answer to a request for quotation before a supplier is listed as silent,
    # days before an offer's validity date or a contract's end that put it on the list. Set in Settings.
    summary_silent_days: int = Field(default=3, ge=1, le=60)
    summary_offer_days: int = Field(default=3, ge=0, le=30)
    summary_contract_days: int = Field(default=90, ge=1, le=365)
    # Second person by risk. A purchase order that meets any rule that is switched on needs a second,
    # different person to confirm it before it is created. All are off (0) until the company sets them in
    # Settings: a total above this many EUR; a supplier with no delivered order yet; a supplier whose bank
    # account was changed in the last N days; a linked contract with an open red remark.
    second_over_eur: float = Field(default=0, ge=0, le=100_000_000)
    second_new_supplier: int = Field(default=0, ge=0, le=1)
    second_bank_days: int = Field(default=0, ge=0, le=365)
    second_legal_red: int = Field(default=0, ge=0, le=1)
    # ABC/XYZ of the articles bought. A: articles up to this cumulative share of spend (percent); B: up to
    # the next; C: the rest. X and Y: coefficient of variation of the monthly quantity up to these values; Z
    # above. The window is the last N calendar months; XYZ needs at least xyz_min_months months of orders in
    # it. The values are common starting points, not facts about the company. Set in Settings.
    abc_a_pct: float = Field(default=80, gt=0, lt=100)
    abc_b_pct: float = Field(default=95, gt=0, le=100)
    xyz_x_max: float = Field(default=0.5, gt=0, le=10)
    xyz_y_max: float = Field(default=1.0, gt=0, le=10)
    abc_window_months: int = Field(default=12, ge=1, le=60)
    xyz_min_months: int = Field(default=3, ge=2, le=24)
    # Sign-in. 0 = the old mode (a name typed at the top, a label in the log); 1 = every request needs a
    # signed-in user and every logged name is that user. Switched in Settings by an administrator.
    # AUTH_FORCE_OFF=true in the environment overrides it for recovery when nobody can sign in.
    auth_enabled: int = Field(default=0, ge=0, le=1)
    auth_force_off: bool = False
    auth_session_hours: int = Field(default=12, ge=1, le=168)
    auth_idle_minutes: int = Field(default=120, ge=5, le=1440)
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
