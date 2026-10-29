"""Settings a person saves in the Settings tab. They are kept in the database (secrets encrypted),
apply on top of the environment, and are never returned to the browser in full."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, env_settings, set_overrides
from app.models import AppSetting, AuditLog
from app.runtime import fx, vault

PROVIDERS = ("mock", "anthropic")
FX_SOURCES = ("manual", "nbs")
SECRET_KEYS = {"anthropic_api_key"}
EDITABLE = {
    "ai_provider",
    "ai_model",
    "anthropic_api_key",
    "fx_source",
    "fx_rsd_per_eur",
    "fx_usd_per_eur",
    "duty_rate_max_age_days",
    "weight_delivery_history",
    "delivery_history_min_orders",
    "invoice_tolerance_pct",
}
FLOATS = {"fx_rsd_per_eur", "fx_usd_per_eur", "invoice_tolerance_pct"}
INTS = {"duty_rate_max_age_days", "weight_delivery_history", "delivery_history_min_orders"}


class SettingsError(ValueError):
    pass


def stored(session: Session, settings: Settings) -> dict:
    """Saved values, decoded. A secret that cannot be decrypted is skipped."""
    out: dict = {}
    for row in session.scalars(select(AppSetting)):
        if row.key not in EDITABLE:
            continue
        value = vault.decrypt(settings, row.value) if row.secret else row.value
        if value is None:
            continue
        out[row.key] = float(value) if row.key in FLOATS else int(value) if row.key in INTS else value
    return out


def overrides(session: Session, settings: Settings) -> dict:
    values = stored(session, settings)
    if values.get("fx_source") == "nbs":
        last = fx.latest(session)
        if last:
            values["fx_rsd_per_eur"], values["fx_usd_per_eur"] = last.rsd_per_eur, last.usd_per_eur
    return values


def apply(session: Session, settings: Settings | None = None) -> dict:
    """Rebuild the in-process overrides from the database."""
    values = overrides(session, settings or env_settings())
    set_overrides(values)
    return values


def save(session: Session, settings: Settings, person: str, values: dict) -> None:
    if not person or not person.strip():
        raise SettingsError("a named person is required for this action")
    person = person.strip()
    shown = {}
    for key, value in values.items():
        if key not in EDITABLE:
            raise SettingsError(f"unknown setting: {key}")
        secret = key in SECRET_KEYS
        text = vault.encrypt(settings, value) if secret else str(value)
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=text, secret=secret, updated_by=person))
        else:
            row.value, row.secret, row.updated_by = text, secret, person
        shown[key] = "(secret, changed)" if secret else value
    session.add(AuditLog(actor="human", actor_id=person, action="settings.update", payload=shown))
    session.commit()


def remove(session: Session, person: str, key: str) -> None:
    if not person or not person.strip():
        raise SettingsError("a named person is required for this action")
    row = session.get(AppSetting, key)
    if row is not None:
        session.delete(row)
    session.add(
        AuditLog(actor="human", actor_id=person.strip(), action="settings.remove", payload={"key": key})
    )
    session.commit()


def key_state(session: Session, settings: Settings) -> dict:
    """Where the Anthropic key comes from, never the key itself."""
    saved = stored(session, settings).get("anthropic_api_key")
    key, where = (saved, "app") if saved else (env_settings().anthropic_api_key, "env")
    if not key:
        return {"set": False, "source": None, "hint": None}
    return {"set": True, "source": where, "hint": "…" + key[-4:]}
