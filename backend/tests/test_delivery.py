"""The delivery record of a purchase order: a first date from the offer's lead time, changes that need a
reason, a status that ends at delivered or cancelled, and what counts as overdue."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models import AuditLog, Offer, PurchaseOrder
from app.pipeline import delivery
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import client  # noqa: F401


def _po(c):
    """An order for one offer with a 10 day lead time (the helper's default)."""
    rid, sids, _ = _setup(c)
    a = _offer(c, rid, sids[0], [10, 20], incoterm="DAP", incoterm_place="Belgrade")
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": a["id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"})
    assert po.status_code == 200, po.text
    return po.json()


def _put(c, po, **body):
    return c.put(f"/orders/{po['id']}/delivery", json={"changed_by": "kartel", **body})


def test_a_new_order_gets_a_calculated_date_that_is_not_yet_a_promise(client):  # noqa: F811
    c = client
    po = _po(c)
    d = c.get(f"/orders/{po['id']}/delivery").json()
    ordered = date.fromisoformat(d["ordered_on"])
    assert d["promised_date"] == (ordered + timedelta(days=10)).isoformat()
    assert d["status"] == "ordered" and "no confirmation" in d["status_label"]
    [first] = d["history"]
    assert (
        first["kind"] == "promised_date"
        and first["old"] is None
        and "lead time of 10 days" in first["reason"]
    )
    listed = c.get(f"/requests/{po['request_id']}/orders").json()[0]
    assert listed["promised_date"] == d["promised_date"] and listed["delivery_status"] == "ordered"


def test_moving_a_date_needs_a_reason_and_leaves_a_history(client):  # noqa: F811
    c = client
    po = _po(c)
    d = c.get(f"/orders/{po['id']}/delivery").json()
    ordered = date.fromisoformat(d["ordered_on"])
    new = (ordered + timedelta(days=21)).isoformat()
    assert _put(c, po, promised_date=new).status_code == 409  # no reason
    assert _put(c, po, promised_date=new, reason="x", changed_by=" ").status_code == 409  # no name
    ok = _put(c, po, promised_date=new, reason="supplier: stock arrives late", status="confirmed")
    assert ok.status_code == 200
    out = ok.json()
    assert out["promised_date"] == new and out["status"] == "confirmed"
    moved = [h for h in out["history"] if h["kind"] == "promised_date"][-1]
    assert (moved["old"], moved["new"], moved["by"]) == (d["promised_date"], new, "kartel")
    assert moved["reason"] == "supplier: stock arrives late"
    n = len(out["history"])
    assert (
        _put(c, po, promised_date=new, reason="same again").json()["history"].__len__() == n
    )  # no change, no event
    before = (ordered - timedelta(days=1)).isoformat()
    assert _put(c, po, promised_date=before, reason="typo").status_code == 409


def test_the_status_runs_to_delivered_and_then_the_record_is_closed(client):  # noqa: F811
    c = client
    po = _po(c)
    assert _put(c, po, status="shipped").json()["status"] == "shipped"
    future = (date.today() + timedelta(days=3)).isoformat()
    assert _put(c, po, status="delivered", delivered_date=future).status_code == 409
    assert _put(c, po, delivered_date=date.today().isoformat()).status_code == 409  # only with delivered
    done = _put(c, po, status="delivered", reason="goods checked in")
    assert done.status_code == 200
    d = done.json()
    assert d["status"] == "delivered" and d["delivered_date"] == date.today().isoformat() and d["final"]
    kinds = [h["kind"] for h in d["history"]]
    assert kinds.count("status") == 2 and "delivered_date" in kinds
    assert (
        _put(c, po, status="shipped").status_code == 409
        and _put(c, po, promised_date="2030-01-01").status_code == 409
    )


def test_what_is_overdue_is_decided_by_code_and_ends_with_delivery_or_cancellation(client):  # noqa: F811
    c = client
    po = _po(c)
    promised = date.fromisoformat(c.get(f"/orders/{po['id']}/delivery").json()["promised_date"])
    assert delivery.view(c.session, po["id"], promised)["overdue_days"] == 0  # on the day itself
    assert delivery.view(c.session, po["id"], promised + timedelta(days=4))["overdue_days"] == 4
    _put(c, po, status="shipped")
    assert (
        delivery.view(c.session, po["id"], promised + timedelta(days=4))["overdue_days"] == 4
    )  # still on the way
    _put(c, po, status="cancelled", reason="customer withdrew")
    assert delivery.view(c.session, po["id"], promised + timedelta(days=4))["overdue_days"] == 0


def test_bad_requests_are_refused_and_changes_are_audited(client):  # noqa: F811
    c = client
    po = _po(c)
    assert _put(c, po, status="lost").status_code == 422
    assert _put(c, po).status_code == 422  # nothing to change
    assert (
        c.put("/orders/9999/delivery", json={"changed_by": "kartel", "status": "shipped"}).status_code == 404
    )
    assert c.get("/orders/9999/delivery").status_code == 404
    _put(c, po, status="confirmed", reason="supplier confirmed by phone")
    rows = c.session.scalars(select(AuditLog).where(AuditLog.action == "po.delivery_updated")).all()
    assert len(rows) == 1 and rows[0].actor_id == "kartel" and rows[0].payload["status"] == "confirmed"


def test_an_order_without_a_date_gets_one_and_the_first_date_needs_no_reason(client):  # noqa: F811
    c = client
    po = _po(c)
    row = c.session.get(PurchaseOrder, po["id"])
    row.promised_date = None  # an order made before the delivery record existed
    c.session.commit()
    assert c.session.get(Offer, row.offer_id) is not None
    day = (date.today() + timedelta(days=15)).isoformat()
    r = _put(c, po, promised_date=day)
    assert r.status_code == 200 and r.json()["promised_date"] == day
    assert r.json()["history"][-1]["reason"] == "first date given"
