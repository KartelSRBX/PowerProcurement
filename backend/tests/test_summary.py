"""The daily summary: one list of what needs a person today, read from records the app already keeps."""

from datetime import UTC, date, datetime, timedelta

from cryptography.fernet import Fernet

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from app.models import Contract, CustomerRequest, Offer, PurchaseOrder, Rfq
from tests.test_comparison import _offer, _setup
from tests.test_delivery import _po
from tests.test_invoice import _inv
from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401
from tests.test_supplier_bank import _body
from tests.test_supplier_duplicates import _add


def _today(c):
    r = c.get("/summary/today")
    assert r.status_code == 200, r.text
    return r.json()


def _sec(c, key):
    return next(s for s in _today(c)["sections"] if s["key"] == key)


def _ago(days):
    return datetime.now(UTC) - timedelta(days=days)


def test_an_empty_day_has_nothing_to_do(client):  # noqa: F811
    s = _today(client)
    assert s["total"] == 0 and s["date"] == date.today().isoformat()
    keys = "urgent approvals deliveries offers silent contracts bank invoices rechecks duplicates"
    assert [x["key"] for x in s["sections"]] == keys.split()
    assert all(x["count"] == 0 and x["items"] == [] for x in s["sections"])


def test_urgent_requests_and_letters_waiting_for_approval(client):  # noqa: F811
    c = client
    rid = new_request(c)
    c.put(f"/requests/{rid}/urgency", json={"changed_by": "kartel", "urgent": True, "respond_by": None})
    c.session.get(CustomerRequest, rid).respond_by = date.today() - timedelta(days=2)
    c.session.commit()
    row = _sec(c, "urgent")["items"][0]
    assert _sec(c, "urgent")["count"] == 1 and row["tone"] == "bad" and "2 day(s) late" in row["text"]
    assert row["href"] == f"/requests/{rid}"
    c.post(f"/requests/{rid}/discover")
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    assert _sec(c, "approvals")["count"] == len(drafts) > 0
    c.post(f"/rfqs/{drafts[0]['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    assert _sec(c, "approvals")["count"] == len(drafts) - 1


def test_late_deliveries(client):  # noqa: F811
    c = client
    po = _po(c)
    row = c.session.get(PurchaseOrder, po["id"])
    row.promised_date = date.today() - timedelta(days=4)
    c.session.commit()
    sec = _sec(c, "deliveries")
    assert (
        sec["count"] == 1
        and "4 day(s) late" in sec["items"][0]["text"]
        and "not asked" in sec["items"][0]["text"]
    )


def test_offers_past_or_near_their_date_and_suppliers_that_have_not_answered(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    assert len(sids) >= 2
    offer = _offer(c, rid, sids[0], [10, 20])
    c.session.get(Offer, offer["id"]).valid_until = date.today() - timedelta(days=1)
    for r in c.session.query(Rfq).filter_by(request_id=rid):
        r.sent_at = _ago(5)
    c.session.commit()
    offers = _sec(c, "offers")
    assert (
        offers["count"] == 1
        and "expired" in offers["items"][0]["text"]
        and offers["items"][0]["tone"] == "bad"
    )
    silent = _sec(c, "silent")
    sent_to = {r.supplier_id for r in c.session.query(Rfq).filter_by(request_id=rid, status="sent")}
    assert silent["count"] == len(sent_to - {sids[0]}) > 0  # the supplier that answered is not silent
    assert all("5 day(s)" in i["text"] for i in silent["items"])
    # a request with an order is no longer waiting on offers or answers
    c.session.add(
        PurchaseOrder(
            request_id=rid,
            offer_id=offer["id"],
            supplier_id=sids[0],
            total_eur=1,
            budget_checks={},
            approved_by="k",
        )
    )
    c.session.commit()
    assert _sec(c, "offers")["count"] == 0 and _sec(c, "silent")["count"] == 0


def test_contracts_that_ended_or_end_soon(client):  # noqa: F811
    c = client

    def add(title, days):
        c.session.add(
            Contract(
                title=title, counterparty="Acme", role="buy", text="x", text_hash="h" + title, created_by="k",
                expires_on=date.today() + timedelta(days=days),
            )
        )  # fmt: skip

    add("Ended", -3)
    add("Soon", 40)
    add("Later", 200)
    c.session.commit()
    sec = _sec(c, "contracts")
    assert sec["count"] == 2
    assert [i["tone"] for i in sec["items"]] == ["bad", "warn"] and "Ended" in sec["items"][0]["text"]


def test_bank_changes_invoices_screenings_and_duplicates(client):  # noqa: F811
    c = client
    key = Fernet.generate_key().decode()
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update={"app_secret_key": key})
    a = _add(c, "Nord Parts", tax_id="RS55566677")
    _add(c, "Sued Bauteile", tax_id="55566677")
    c.post(f"/suppliers/{a}/bank/proposals", json=_body(holder="Nord Parts"))
    assert _sec(c, "bank")["count"] == 1 and "kartel" in _sec(c, "bank")["items"][0]["text"]
    dup = _sec(c, "duplicates")
    assert dup["count"] == 1 and "same tax number" in dup["items"][0]["text"]
    c.post(
        f"/suppliers/{a}/screenings",
        json={
            "checked_by": "k",
            "checked_on": "2026-01-01",
            "list_name": "L",
            "result": "match",
            "note": "same name",
        },
    )
    assert "needs attention" in _sec(c, "rechecks")["items"][0]["text"]
    po = _po(c)
    assert _inv(c, po, total_net=47000).status_code == 200  # 2,000 above the order
    inv = _sec(c, "invoices")
    assert inv["count"] == 1 and "+2000.00 EUR" in inv["items"][0]["text"]
    assert _today(c)["total"] == sum(s["count"] for s in _today(c)["sections"]) >= 4


def test_the_thresholds_are_settings(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    for r in c.session.query(Rfq).filter_by(request_id=rid):
        r.sent_at = _ago(5)
    c.session.commit()
    assert _sec(c, "silent")["count"] > 0  # 3 days by default
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    try:
        body = {"changed_by": "kartel", "silent_days": 10, "offer_days": 3, "contract_days": 90}
        assert c.put("/settings/summary", json={**body, "changed_by": " "}).status_code == 422
        assert c.put("/settings/summary", json={**body, "silent_days": 0}).status_code == 422
        r = c.put("/settings/summary", json=body)
        assert r.status_code == 200 and r.json()["summary"] == {
            "silent_days": 10,
            "offer_days": 3,
            "contract_days": 90,
        }
        assert _sec(c, "silent")["count"] == 0
    finally:
        set_overrides({})
