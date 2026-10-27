"""What an Incoterms rule leaves to the buyer (from the Legal module's data) and the warning when a tariff's
rates are old. The tariff in these tests is the invented sample; no real data is stored."""

from datetime import date, timedelta
from pathlib import Path

from app.config import get_settings, set_overrides
from app.duty import service
from app.duty.parser import parse_lines
from app.legal import incoterms
from app.pricing.incoterm_notes import carriage_flag, you_pay
from app.runtime import store
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401

SAMPLE = Path(__file__).parent / "fixtures" / "duty" / "sample_tariff.txt"
CODE = "9901101000"  # a line of the invented sample


def _load(c, rate_date):
    lines = parse_lines(SAMPLE.read_text(encoding="utf-8").splitlines())
    service.import_lines(c.session, lines, "invented sample tariff", rate_date, "kartel")


def _body(code=CODE, **over):
    body = {
        "currency": "EUR",
        "incoterm": "FOB",
        "lines": [{"description": "A", "quantity": 10, "unit_price": 60, "hs_code": code, "duty_pct": 15}],
        "freight": 100,
        "insurance": 10,
        "inland": 20,
        "clearance": 10,
        "vat_pct": 20,
    }
    return body | over


def test_you_pay_follows_the_rule_and_quotes_the_legal_data():
    fob = you_pay("fob")
    who = {ln["key"]: ln["pays"] for ln in fob["lines"]}
    assert who == {
        "origin": "seller",
        "carriage": "you",
        "insurance": "you",
        "delivery": "you",
        "import_taxes": "you",
    }
    legal = {t["key"]: t for t in incoterms.build("FOB")["topics"]}
    carriage = next(ln for ln in fob["lines"] if ln["key"] == "carriage")
    assert carriage["text"] == legal["carriage"]["buyer"]  # the words are the Legal module's, not ours
    origin = next(ln for ln in fob["lines"] if ln["key"] == "origin")
    assert origin["text"] == legal["clearance"]["seller"]
    assert "main carriage" in fob["summary"] and fob["watch"] == incoterms.build("FOB")["watch"]["buy"]
    assert [ln["pays"] for ln in you_pay("DAP")["lines"]] == ["seller"] * 4 + ["you"]
    assert "seller pays everything" in you_pay("DDP")["summary"]
    assert all(ln["pays"] == "you" for ln in you_pay("EXW")["lines"])
    assert you_pay("XYZ") is None and you_pay(None) is None


def test_only_the_rules_that_leave_carriage_to_the_buyer_raise_the_carriage_flag():
    assert carriage_flag("FOB") == "FOB: you pay the main carriage, it is not in this price"
    flagged = {c for c in incoterms.CODES if carriage_flag(c)}
    assert flagged == {"EXW", "FCA", "FAS", "FOB"}
    assert carriage_flag(None) is None and carriage_flag("CIF") is None


def test_an_fob_offer_is_flagged_in_the_score_table_and_a_dap_offer_is_not(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    fob = _offer(c, rid, sids[0], [10, 20], incoterm="FOB", incoterm_place="Shanghai")
    dap = _offer(c, rid, sids[1], [12, 15], incoterm="DAP", incoterm_place="Belgrade")
    rows = {r["offer_id"]: r for r in c.post(f"/requests/{rid}/score").json()}
    assert any("you pay the main carriage" in f for f in rows[fob["id"]]["term_flags"])
    assert not any("main carriage" in f for f in rows[dap["id"]]["term_flags"])


def test_the_calculation_says_what_you_pay_under_its_rule(client):  # noqa: F811
    d = client.post("/pricing/landed", json=_body()).json()
    assert d["you_pay"]["code"] == "FOB" and d["you_pay"]["lines"][1]["pays"] == "you"
    assert client.post("/pricing/landed", json=_body(incoterm=None)).json()["you_pay"] is None


def test_an_old_tariff_adds_a_warning_but_the_result_stays_complete(client):  # noqa: F811
    c = client
    _load(c, date.today() - timedelta(days=400))
    d = c.post("/pricing/landed", json=_body()).json()
    assert d["complete"]
    [check] = d["rate_checks"]
    assert check["state"] == "old" and check["code"] == CODE
    assert any("400 days ago (limit 365)" in w for w in d["warnings"])


def test_a_recent_tariff_has_no_warning(client):  # noqa: F811
    c = client
    _load(c, date.today() - timedelta(days=30))
    d = c.post("/pricing/landed", json=_body()).json()
    assert d["rate_checks"][0]["state"] == "ok" and not d["warnings"]


def test_a_tariff_without_a_date_is_unknown_not_fresh(client):  # noqa: F811
    c = client
    _load(c, None)
    d = c.post("/pricing/landed", json=_body()).json()
    assert d["rate_checks"][0]["state"] == "unknown" and any("no rate date" in w for w in d["warnings"])
    assert c.get("/duties/summary").json()["freshness"]["state"] == "unknown"


def test_a_code_that_is_missing_or_partial_is_said_so(client):  # noqa: F811
    c = client
    _load(c, date.today())
    gone = c.post("/pricing/landed", json=_body(code="9999999999")).json()
    assert gone["rate_checks"][0]["state"] == "not found" and any(
        "not in the duty registry" in w for w in gone["warnings"]
    )
    part = c.post("/pricing/landed", json=_body(code="9901 10")).json()
    assert part["rate_checks"][0]["state"] == "incomplete" and any(
        "not a full 10-digit" in w for w in part["warnings"]
    )
    none = c.post("/pricing/landed", json=_body(code=None)).json()
    assert none["rate_checks"] == [] and not none["warnings"]


def test_without_any_tariff_loaded_the_check_says_so(client):  # noqa: F811
    d = client.post("/pricing/landed", json=_body()).json()
    assert d["rate_checks"][0]["state"] == "not found" and any(
        "no tariff is loaded" in w for w in d["warnings"]
    )


def test_the_limit_is_a_setting_a_named_person_changes(client):  # noqa: F811
    c = client
    _load(c, date.today() - timedelta(days=400))
    assert c.get("/duties/summary").json()["freshness"]["state"] == "old"
    assert c.put("/duties/settings", json={"changed_by": " ", "max_age_days": 500}).status_code == 422
    assert c.put("/duties/settings", json={"changed_by": "kartel", "max_age_days": 10}).status_code == 422
    try:
        r = c.put("/duties/settings", json={"changed_by": "kartel", "max_age_days": 500})
        assert r.status_code == 200 and r.json()["freshness"]["state"] == "ok"
        assert store.stored(c.session, SETTINGS)["duty_rate_max_age_days"] == 500
        assert get_settings().duty_rate_max_age_days == 500  # the running app now uses it
    finally:
        set_overrides({})


def test_the_code_lookup_carries_the_age_of_its_rates(client):  # noqa: F811
    c = client
    _load(c, date.today() - timedelta(days=400))
    one = c.get(f"/duties/{CODE}").json()
    assert one["freshness"]["state"] == "old" and one["freshness"]["age_days"] == 400
