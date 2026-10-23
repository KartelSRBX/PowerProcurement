"""Walks one request from confirmed to purchase order through the HTTP API, with synthetic data,
no AI, and SMTP replaced by a recorder. This is the skeleton's acceptance test."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_session
from app.main import app
from app.models import AuditLog, PriceEvent
from app.seed import seed

SETTINGS = Settings(_env_file=None, smtp_host="mailpit")
FUTURE = "2027-06-01"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed(session, SETTINGS)
    outbox = []

    class RecordingSMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, msg):
            outbox.append(
                {
                    "to": msg["To"],
                    "subject": msg["Subject"],
                    "approved_by": msg["X-Approved-By"],
                    "message_id": msg["Message-ID"],
                }
            )

    monkeypatch.setattr("app.mail.sender.smtplib.SMTP", RecordingSMTP)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    c = TestClient(app)
    c.outbox, c.session = outbox, session
    yield c
    app.dependency_overrides.clear()
    session.close()


def new_request(c, **over):
    parsed = {
        "is_request": True,
        "language": "en",
        "category": "electronics",
        "confidence": 1.0,
        "items": [
            {"description": "STM32F407VGT6 microcontroller", "quantity": 500},
            {"description": "100nF 0603 capacitors", "quantity": 2000},
        ],
        "needed_by": FUTURE,
        "delivery_country": "RS",
        **over,
    }
    r = c.post(
        "/requests/manual",
        json={
            "sender": "buyer@customer.example",
            "subject": "RFQ",
            "body": "x",
            "parsed": parsed,
            "confirmed_by": "kartel",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def run_to_offers(c, rid):
    assert c.post(f"/requests/{rid}/discover").status_code == 200
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    for d in drafts:
        r = c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
        assert r.json()["status"] == "sent"
    assert c.post(f"/requests/{rid}/offers/simulate").status_code == 200


def test_full_flow_from_request_to_purchase_order(client):
    c = client
    rid = new_request(c)
    assert c.get(f"/requests/{rid}/pipeline").json()["stage"] == "confirmed"

    # steps 2-3: shortlist and target prices, every price labelled unconfirmed with its source
    disc = c.post(f"/requests/{rid}/discover").json()
    assert disc["shortlist"] >= 2 and disc["items_with_target"] == 2 and disc["target_total_eur"] > 0
    names = [s["supplier"] for s in c.get(f"/requests/{rid}/shortlist").json()]
    assert "Vostok Parts Trading" not in names  # sanctioned supplier never shortlisted
    prices = c.get(f"/requests/{rid}/market-prices").json()
    assert prices and all(
        p["source"] and p["valid_until"] and p["label"].startswith("unconfirmed") for p in prices
    )

    # step 4: drafts exist, nothing has been sent, a named approver is required
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    assert drafts and all(d["status"] == "draft" for d in drafts) and c.outbox == []
    assert (
        c.post(f"/rfqs/{drafts[0]['id']}/decision", json={"approve": True, "decided_by": " "}).status_code
        == 409
    )
    assert c.outbox == []
    edited = c.patch(f"/rfqs/{drafts[0]['id']}", json={"body": "edited by a person"}).json()
    assert edited["body"] == "edited by a person"
    c.post(f"/rfqs/{drafts[1]['id']}/decision", json={"approve": False, "decided_by": "kartel"})
    for d in [drafts[0], *drafts[2:]]:
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    assert len(c.outbox) == len(drafts) - 1 and all(m["approved_by"] == "kartel" for m in c.outbox)
    assert c.get(f"/requests/{rid}/pipeline").json()["stage"] == "rfq_sent"

    # step 5: offers and deterministic scoring
    assert c.post(f"/requests/{rid}/offers/simulate").status_code == 200
    ranked = c.post(f"/requests/{rid}/score").json()
    assert ranked and ranked[0]["excluded"] is None
    assert c.post(f"/requests/{rid}/score").json() == ranked  # same inputs, same result
    best = ranked[0]
    heavy_price = c.post(
        f"/requests/{rid}/score",
        json={"price": 100, "lead_time": 0, "reliability": 0, "terms": 0, "external_risk": 0},
    ).json()
    cheapest = min((r for r in heavy_price if r["excluded"] is None), key=lambda r: r["landed_cost_eur"])
    assert heavy_price[0]["landed_cost_eur"] == cheapest["landed_cost_eur"]

    # step 6: quote with markup in RSD, then approval sends it to the customer
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.2, "currency": "RSD", "created_by": "kartel"},
    ).json()
    assert q["price"] == pytest.approx(best["landed_cost_eur"] * 1.2 * 117, rel=1e-3)
    n = len(c.outbox)
    assert c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).status_code == 409  # too early
    sent = c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"}).json()
    assert sent["status"] == "sent" and c.outbox[n]["to"] == "buyer@customer.example"

    # step 7 -> 8: the order only exists after the customer says yes
    assert c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).status_code == 409
    o = c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    assert o.status_code == 200
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).json()
    assert po["budget_checks"]["not_below_cost"] and po["budget_checks"]["within_po_limit"]
    assert c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).status_code == 409  # only one PO
    inv = c.post(f"/orders/{po['id']}/invoice-request", json={"approved_by": "kartel"}).json()
    assert inv["invoice_requested_by"] == "kartel"
    assert c.get(f"/requests/{rid}/pipeline").json()["stage"] == "invoice_requested"

    # every price change has a date and an author kind; every human decision is in the audit log
    events = c.session.scalars(select(PriceEvent).where(PriceEvent.request_id == rid)).all()
    assert {e.actor for e in events} >= {"system", "human"} and all(e.created_at for e in events)
    actions = {a.action for a in c.session.scalars(select(AuditLog))}
    assert {
        "rfq.approved",
        "rfq.rejected",
        "quote.approved",
        "outcome.recorded",
        "po.approved",
        "invoice.requested",
    } <= actions


def test_no_order_without_acceptance_and_no_order_below_cost(client):
    c = client
    rid = new_request(c)
    run_to_offers(c, rid)
    best = c.post(f"/requests/{rid}/score").json()[0]
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": -0.5, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "counter", "price": 100, "confirmed_by": "kartel"})
    assert (
        c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).status_code == 409
    )  # not accepted
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "price": 100, "confirmed_by": "kartel"})
    r = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"})
    assert r.status_code == 409 and "not_below_cost" in r.json()["detail"]


def test_missing_quantity_blocks_discovery(client):
    rid = new_request(client, items=[{"description": "STM32F407VGT6", "quantity": None}])
    r = client.post(f"/requests/{rid}/discover")
    assert r.status_code == 409 and "quantity" in r.json()["detail"]


def test_sanctioned_offer_cannot_be_quoted_and_is_excluded(client):
    c = client
    rid = new_request(c)
    vostok = next(s for s in c.get("/suppliers").json() if s["sanctioned"])
    c.post(
        f"/requests/{rid}/offers",
        json={"supplier_id": vostok["id"], "total_price": 1.0, "currency": "EUR", "lead_time_days": 1},
    )
    ranked = c.post(f"/requests/{rid}/score").json()
    assert ranked[0]["excluded"] == "sanctions list match"
    r = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": ranked[0]["offer_id"], "currency": "EUR", "created_by": "kartel"},
    )
    assert r.status_code == 409
