from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.runtime import fx, store

router = APIRouter(prefix="/settings", tags=["settings"])

# Replaced in tests; given the key, model and a short prompt it returns a one-line result.
KEY_PREFIX = "sk-ant-"


class AiIn(BaseModel):
    changed_by: str
    provider: str
    model: str
    api_key: str | None = None  # empty or missing keeps the saved key
    clear_key: bool = False


class FxIn(BaseModel):
    changed_by: str
    source: str
    rsd_per_eur: float | None = None
    usd_per_eur: float | None = None


class ScoringIn(BaseModel):
    changed_by: str
    delivery_history_weight: int = Field(ge=0, le=100)
    delivery_history_min_orders: int = Field(ge=2, le=50)


class InvoicesIn(BaseModel):
    changed_by: str
    tolerance_pct: float = Field(ge=0, le=20)


class WhoIn(BaseModel):
    changed_by: str


def _effective(session: Session, base: Settings) -> Settings:
    return base.model_copy(update=store.overrides(session, base))


def _view(session: Session, base: Settings) -> dict:
    eff = _effective(session, base)
    saved = store.stored(session, base)
    last = fx.latest(session)
    return {
        "ai": {
            "provider": eff.ai_provider,
            "model": eff.ai_model,
            "key": store.key_state(session, base),
            "providers": list(store.PROVIDERS),
        },
        "fx": {
            "source": eff.fx_source,
            "rsd_per_eur": eff.fx_rsd_per_eur,
            "usd_per_eur": eff.fx_usd_per_eur,
            "manual_rsd_per_eur": saved.get("fx_rsd_per_eur", base.fx_rsd_per_eur),
            "manual_usd_per_eur": saved.get("fx_usd_per_eur", base.fx_usd_per_eur),
            "rate_date": last.rate_date.isoformat() if last else None,
            "fetched_at": last.fetched_at.isoformat() if last else None,
            "url": base.fx_nbs_url,
            "history": [
                {
                    "rate_date": r.rate_date.isoformat(),
                    "rsd_per_eur": r.rsd_per_eur,
                    "usd_per_eur": r.usd_per_eur,
                    "fetched_at": r.fetched_at.isoformat(),
                }
                for r in fx.history(session)
            ],
        },
        "invoices": {"tolerance_pct": eff.invoice_tolerance_pct},
        "scoring": {
            "delivery_history_weight": eff.weight_delivery_history,
            "delivery_history_min_orders": eff.delivery_history_min_orders,
        },
    }


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


@router.get("")
def read(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    return _view(session, settings)


@router.put("/ai")
def save_ai(body: AiIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if body.provider not in store.PROVIDERS:
        raise _bad(ValueError(f"provider must be one of {', '.join(store.PROVIDERS)}"))
    model = body.model.strip()
    if not model:
        raise _bad(ValueError("model name is required"))
    values: dict = {"ai_provider": body.provider, "ai_model": model}
    key = (body.api_key or "").strip()
    if key:
        if not key.startswith(KEY_PREFIX) or len(key) < 30 or any(c.isspace() for c in key):
            raise _bad(
                ValueError(f"that does not look like an Anthropic API key (it starts with {KEY_PREFIX})")
            )
        values["anthropic_api_key"] = key
    try:
        if body.clear_key:
            store.remove(session, body.changed_by, "anthropic_api_key")
        has_key = bool(key) or (not body.clear_key and store.key_state(session, settings)["set"])
        if body.provider == "anthropic" and not has_key:
            raise store.SettingsError("save an API key first, or choose the mock provider")
        store.save(session, settings, body.changed_by, values)
        store.apply(session, settings)
    except store.SettingsError as exc:
        session.rollback()
        raise _bad(exc) from exc
    return _view(session, settings)


@router.post("/ai/test")
def test_ai(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    """One tiny call with the saved key, to tell the person at once whether it works."""
    eff = _effective(session, settings)
    if not eff.anthropic_api_key:
        return {"ok": False, "detail": "No API key is saved."}
    return check_key(eff.anthropic_api_key, eff.ai_model)


def check_key(api_key: str, model: str) -> dict:
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=20)
        client.messages.create(
            model=model, max_tokens=8, messages=[{"role": "user", "content": "Reply with OK."}]
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "detail": "The key was rejected (401). Check that it is copied in full."}
    except anthropic.PermissionDeniedError:
        return {"ok": False, "detail": "The key has no access to this model or workspace (403)."}
    except anthropic.NotFoundError:
        return {"ok": False, "detail": f"Model “{model}” was not found for this key."}
    except anthropic.RateLimitError:
        return {"ok": False, "detail": "The key works but is rate limited right now (429). Try again later."}
    except anthropic.APIConnectionError:
        return {"ok": False, "detail": "Cannot reach api.anthropic.com from this machine."}
    except anthropic.APIError as exc:
        return {"ok": False, "detail": f"The API answered with an error ({type(exc).__name__})."}
    return {"ok": True, "detail": f"The key works with {model}."}


@router.put("/fx")
def save_fx(body: FxIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if body.source not in store.FX_SOURCES:
        raise _bad(ValueError(f"source must be one of {', '.join(store.FX_SOURCES)}"))
    values: dict = {"fx_source": body.source}
    for key, v in (("fx_rsd_per_eur", body.rsd_per_eur), ("fx_usd_per_eur", body.usd_per_eur)):
        if v is not None:
            if not 0 < v < 100000:
                raise _bad(ValueError("exchange rates must be positive numbers"))
            values[key] = v
    try:
        if body.source == "nbs" and fx.latest(session) is None:
            fx.refresh(session, settings)
        store.save(session, settings, body.changed_by, values)
        store.apply(session, settings)
    except fx.FxError as exc:
        session.rollback()
        raise HTTPException(502, f"Could not fetch National Bank of Serbia rates: {exc}") from exc
    except store.SettingsError as exc:
        session.rollback()
        raise _bad(exc) from exc
    return _view(session, settings)


@router.put("/scoring")
def save_scoring(
    body: ScoringIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    """Weight of the delivery-history criterion and how many delivered orders a supplier needs for it."""
    try:
        store.save(
            session,
            settings,
            body.changed_by,
            {
                "weight_delivery_history": body.delivery_history_weight,
                "delivery_history_min_orders": body.delivery_history_min_orders,
            },
        )
        store.apply(session, settings)
    except store.SettingsError as exc:
        session.rollback()
        raise _bad(exc) from exc
    return _view(session, settings)


@router.put("/invoices")
def save_invoices(
    body: InvoicesIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    """How far a supplier invoice may differ from its order before it is shown as differing."""
    try:
        store.save(session, settings, body.changed_by, {"invoice_tolerance_pct": body.tolerance_pct})
        store.apply(session, settings)
    except store.SettingsError as exc:
        session.rollback()
        raise _bad(exc) from exc
    return _view(session, settings)


@router.post("/fx/refresh")
def refresh_fx(
    body: WhoIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    if not body.changed_by.strip():
        raise _bad(ValueError("a named person is required for this action"))
    try:
        row = fx.refresh(session, settings)
        store.save(session, settings, body.changed_by, {"fx_source": "nbs"})
        store.apply(session, settings)
    except fx.FxError as exc:
        session.rollback()
        raise HTTPException(502, f"Could not fetch National Bank of Serbia rates: {exc}") from exc
    return {**_view(session, settings), "fetched": row.rate_date.isoformat()}
