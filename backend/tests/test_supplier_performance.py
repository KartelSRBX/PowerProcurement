"""Supplier performance from delivery records: on time against two dates, the spread of the real lead time
against the quoted one, the date moves, and an honest "too few orders" note. Dates are set on the orders."""

from datetime import UTC, date, datetime

from app.models import DeliveryEvent, Offer, PurchaseOrder
from app.suppliers.performance import performance
from tests.test_delivery import _po
from tests.test_pipeline_e2e import client  # noqa: F401


def _order(c, supplier_id, ordered, first, final, delivered, status="delivered", moves=()):
    """An order for the supplier with the given dates (ISO strings). `moves` are further dates the promise
    was moved to, after `first`, ending at `final`."""
    po = _po(c)
    row = c.session.get(PurchaseOrder, po["id"])
    row.supplier_id = supplier_id
    row.created_at = datetime.fromisoformat(ordered).replace(tzinfo=UTC)
    row.promised_date = date.fromisoformat(final) if final else None
    row.delivery_status = status
    row.delivered_date = date.fromisoformat(delivered) if delivered else None
    c.session.get(Offer, row.offer_id).lead_time_days = 10
    for e in c.session.query(DeliveryEvent).filter_by(order_id=row.id).all():
        c.session.delete(e)
    c.session.flush()
    prev = None
    for d in (first, *moves):
        c.session.add(
            DeliveryEvent(
                order_id=row.id, kind="promised_date", old_value=prev, new_value=d, reason="t", changed_by="k"
            )
        )
        prev = d
    c.session.commit()
    return row.id


def _supplier(c):
    return c.get("/suppliers").json()[0]["id"]


def _four(c, sid):
    _order(c, sid, "2026-01-01", "2026-01-11", "2026-01-11", "2026-01-11")  # on time, 10 days
    _order(c, sid, "2026-01-01", "2026-01-11", "2026-01-16", "2026-01-15", moves=("2026-01-16",))  # 14 days
    _order(c, sid, "2026-02-01", "2026-02-11", "2026-02-11", "2026-02-14")  # 3 days late, 13 days
    _order(c, sid, "2026-03-01", "2026-03-11", "2026-03-11", "2026-03-09")  # early, 8 days


def test_on_time_against_both_dates_and_the_lead_time_spread_match_a_hand_calculation(client):  # noqa: F811
    c = client
    sid = _supplier(c)
    _four(c, sid)
    p = performance(c.session, sid, today=date(2026, 4, 1))
    assert p["orders"]["delivered"] == 4 and p["enough"] and p["note"] == ""
    # against the date in force: A on time, B 1 day early, C 3 days late, D 2 days early -> 3 of 4
    assert p["on_time"]["pct"] == 75.0 and p["on_time"]["of"] == 4
    # against the first date: A on time, B 4 days late, C 3 late, D early -> 2 of 4
    assert p["on_time_first"]["pct"] == 50.0
    assert p["avg_days_late_when_late"] == 3.0  # only C was late against its final date
    assert p["date_moves"] == {"later": 1, "orders": 1}
    lt = p["lead_time"]
    # real lead times 10, 14, 13, 8: mean 11.25, median 11.5, population stdev sqrt(22.75 / 4) = 2.38
    assert lt["actual"] == {"min": 8, "max": 14, "mean": 11.2, "median": 11.5, "stdev": 2.4}
    assert lt["quoted_mean"] == 10 and lt["actual_minus_quoted"] == 1.2
    assert p["in_full"]["pct"] is None and "no received quantity" in p["in_full"]["note"]


def test_the_latest_orders_are_listed_with_their_own_numbers(client):  # noqa: F811
    c = client
    sid = _supplier(c)
    _four(c, sid)
    recent = performance(c.session, sid, today=date(2026, 4, 1))["recent"]
    assert [r["delivered_date"] for r in recent] == ["2026-03-09", "2026-02-14", "2026-01-15", "2026-01-11"]
    c_row = recent[1]
    assert c_row["actual_days"] == 13 and c_row["days_vs_promise"] == 3 and c_row["days_vs_first"] == 3
    b_row = recent[2]
    assert b_row["days_vs_promise"] == -1 and b_row["days_vs_first"] == 4 and b_row["date_moves"] == 1


def test_too_few_orders_are_said_not_hidden(client):  # noqa: F811
    c = client
    sid = _supplier(c)
    _order(c, sid, "2026-01-01", "2026-01-11", "2026-01-11", "2026-01-12")
    p = performance(c.session, sid, today=date(2026, 4, 1))
    assert not p["enough"] and "only 1 delivered order(s)" in p["note"] and p["on_time"]["pct"] == 0.0
    assert performance(c.session, sid, today=date(2026, 4, 1), min_orders=1)["enough"]


def test_open_cancelled_and_overdue_orders_are_counted_apart_and_never_flatter_the_rate(client):  # noqa: F811
    c = client
    sid = _supplier(c)
    _four(c, sid)
    _order(c, sid, "2026-03-01", "2026-03-11", "2026-03-11", None, status="shipped")  # open and late
    _order(c, sid, "2026-03-01", "2026-04-20", "2026-04-20", None, status="confirmed")  # open, not late yet
    _order(c, sid, "2026-03-01", "2026-03-11", "2026-03-11", None, status="cancelled")
    p = performance(c.session, sid, today=date(2026, 4, 1))
    o = p["orders"]
    assert (o["total"], o["delivered"], o["open"], o["cancelled"], o["overdue_now"]) == (7, 4, 2, 1, 1)
    assert p["on_time"]["pct"] == 75.0  # an open order is not on time yet: it is not in the rate at all


def test_an_order_without_a_date_is_left_out_of_the_on_time_rate_not_counted_as_on_time(client):  # noqa: F811
    c = client
    sid = _supplier(c)
    _four(c, sid)
    _order(c, sid, "2026-03-01", "2026-03-11", None, "2026-03-20")  # delivered, but no promised date
    p = performance(c.session, sid, today=date(2026, 4, 1))
    assert p["orders"]["delivered"] == 5 and p["on_time"]["of"] == 4 and p["on_time"]["pct"] == 75.0


def test_a_supplier_without_orders_has_empty_figures_and_other_suppliers_orders_do_not_count(client):  # noqa: F811
    c = client
    ids = [s["id"] for s in c.get("/suppliers").json()]
    _four(c, ids[0])
    empty = performance(c.session, ids[1], today=date(2026, 4, 1))
    assert (
        empty["orders"]["total"] == 0
        and empty["on_time"]["pct"] is None
        and empty["lead_time"]["actual"] is None
    )
    assert not empty["enough"] and "only 0 delivered" in empty["note"] and empty["recent"] == []


def test_the_supplier_profile_carries_the_performance(client):  # noqa: F811
    c = client
    sid = _supplier(c)
    _four(c, sid)
    d = c.get(f"/suppliers/{sid}").json()
    assert d["performance"]["orders"]["delivered"] == 4 and d["performance"]["on_time"]["pct"] == 75.0
