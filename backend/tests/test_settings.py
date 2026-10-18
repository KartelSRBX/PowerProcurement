"""Keys and exchange-rate source entered in the Settings tab."""

from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app import config
from app.config import Settings, get_settings, set_overrides
from app.main import app
from app.models import AppSetting, AuditLog, FxRate
from app.runtime import api as settings_api
from app.runtime import fx
from tests.test_pipeline_e2e import client  # noqa: F401

KEY = "sk-ant-api03-TESTKEY0123456789abcdefghijklmnopqrstuv-wxyz"
WHO = {"changed_by": "Kartel"}


@pytest.fixture
def c(client, tmp_path):  # noqa: F811
    cfg = Settings(_env_file=None, data_dir=str(tmp_path))
    # the same thing the real get_settings does: environment values with saved ones on top
    app.dependency_overrides[get_settings] = lambda: cfg.model_copy(update=dict(config._overrides))
    set_overrides({})
    yield client
    set_overrides({})


def save_ai(c, **over):
    body = {**WHO, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": KEY, **over}
    return c.put("/settings/ai", json=body)


def test_key_is_saved_encrypted_applied_and_never_returned(c):
    r = save_ai(c)
    assert r.status_code == 200, r.text
    assert KEY not in r.text
    ai = r.json()["ai"]
    assert ai["provider"] == "anthropic" and ai["key"] == {"set": True, "source": "app", "hint": "…wxyz"}
    assert KEY not in c.get("/settings").text
    row = c.session.get(AppSetting, "anthropic_api_key")
    assert row.secret and KEY not in row.value and "TESTKEY" not in row.value
    assert config.get_settings().anthropic_api_key == KEY
    assert config.get_settings().ai_provider == "anthropic"
    log = [a.payload for a in c.session.scalars(select(AuditLog).where(AuditLog.action == "settings.update"))]
    assert log and KEY not in str(log)


def test_saving_needs_a_person_a_valid_key_and_a_key_for_the_live_provider(c):
    assert save_ai(c, changed_by=" ").status_code == 422
    assert save_ai(c, api_key="not-a-key").status_code == 422
    r = save_ai(c, api_key=None)
    assert r.status_code == 422 and "API key" in r.json()["detail"]
    assert c.put("/settings/ai", json={**WHO, "provider": "mock", "model": "m"}).status_code == 200


def test_empty_key_keeps_the_saved_one_and_clear_removes_it(c):
    save_ai(c)
    r = save_ai(c, api_key="", model="claude-haiku-5-5")
    assert (
        r.status_code == 200
        and r.json()["ai"]["key"]["set"]
        and r.json()["ai"]["model"] == "claude-haiku-5-5"
    )
    r = c.put("/settings/ai", json={**WHO, "provider": "mock", "model": "m", "clear_key": True})
    assert r.json()["ai"]["key"]["set"] is False
    assert c.session.get(AppSetting, "anthropic_api_key") is None


def test_connection_test_reports_without_leaking_the_key(c, monkeypatch):
    assert c.post("/settings/ai/test").json()["ok"] is False
    save_ai(c)
    seen = {}

    def fake(key, model):
        seen["key"], seen["model"] = key, model
        return {"ok": True, "detail": "The key works with " + model + "."}

    monkeypatch.setattr(settings_api, "check_key", fake)
    r = c.post("/settings/ai/test").json()
    assert r["ok"] and seen == {"key": KEY, "model": "claude-sonnet-5-5"} and KEY not in str(r)


def payload(code, middle, parity=1, day="2026-10-17"):
    return {"code": code, "date": day, "parity": parity, "exchange_middle": middle}


def nbs_client(answers):
    def handler(request):
        code = request.url.path.split("/")[-3].upper()
        if code not in answers:
            return httpx.Response(404)
        return httpx.Response(200, json=answers[code])

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_nbs_rates_become_units_per_eur():
    got = fx.fetch_nbs(
        Settings(_env_file=None), nbs_client({"EUR": payload("EUR", 117.4), "USD": payload("USD", 104.56)})
    )
    assert got["rsd_per_eur"] == 117.4 and got["rate_date"] == date(2026, 10, 17)
    assert got["usd_per_eur"] == pytest.approx(117.4 / 104.56)
    per100 = fx.fetch_nbs(
        Settings(_env_file=None),
        nbs_client({"EUR": payload("EUR", 11740, 100), "USD": payload("USD", 104.56)}),
    )
    assert per100["rsd_per_eur"] == pytest.approx(117.4)


def test_nbs_errors_are_plain_messages():
    s = Settings(_env_file=None)
    with pytest.raises(fx.FxError, match="404"):
        fx.fetch_nbs(s, nbs_client({}))
    with pytest.raises(fx.FxError, match="exchange_middle"):
        fx.fetch_nbs(s, nbs_client({"EUR": {"date": "2026-10-17"}, "USD": payload("USD", 1)}))


def test_refresh_switches_the_whole_app_to_the_nbs_rate(c, monkeypatch):
    monkeypatch.setattr(
        fx,
        "fetch_nbs",
        lambda s, http=None: {"rate_date": date(2026, 10, 17), "rsd_per_eur": 117.4, "usd_per_eur": 1.12},
    )
    r = c.post("/settings/fx/refresh", json=WHO)
    assert r.status_code == 200, r.text
    body = r.json()["fx"]
    assert body["source"] == "nbs" and body["rsd_per_eur"] == 117.4 and body["rate_date"] == "2026-10-17"
    assert config.get_settings().fx_rsd_per_eur == 117.4 and config.get_settings().fx_usd_per_eur == 1.12
    assert c.session.scalars(select(FxRate)).first().source == "nbs"
    # prices shown in the Suppliers tab follow the new rate
    cfg = c.get("/config").json()
    assert cfg["fx_rsd_per_eur"] == 117.4


def test_fx_fetch_failure_is_a_clear_502_and_changes_nothing(c, monkeypatch):
    def boom(s, http=None):
        raise fx.FxError("cannot reach https://x: ConnectError")

    monkeypatch.setattr(fx, "fetch_nbs", boom)
    r = c.post("/settings/fx/refresh", json=WHO)
    assert r.status_code == 502 and "National Bank of Serbia" in r.json()["detail"]
    assert config.get_settings().fx_rsd_per_eur == 117.0


def test_manual_rates_and_source_validation(c):
    r = c.put("/settings/fx", json={**WHO, "source": "manual", "rsd_per_eur": 118.5, "usd_per_eur": 1.1})
    assert r.status_code == 200 and config.get_settings().fx_rsd_per_eur == 118.5
    assert c.put("/settings/fx", json={**WHO, "source": "manual", "rsd_per_eur": -1}).status_code == 422
    assert c.put("/settings/fx", json={**WHO, "source": "ecb"}).status_code == 422
