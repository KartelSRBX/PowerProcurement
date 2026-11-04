"""ABC/XYZ of the articles bought: ABC by cumulative spend, XYZ by the steadiness of the monthly quantity,
boundaries from Settings, nothing guessed when the history is thin."""

from datetime import UTC, date, datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app import config
from app.analytics import abcxyz
from app.config import get_settings, set_overrides
from app.main import app
from app.models import OfferLine, PurchaseOrder, RequestItem
from tests.test_comparison import _offer
from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401


@pytest.fixture
def c(client):  # noqa: F811
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    yield client
    set_overrides({})


def _ordered(c, items, when=None, price=1.0):
    """One purchase order for `items` [(description, quantity)] at `price` EUR each, dated `when`."""
    # discovery needs articles the demo suppliers know, so the request is made with those and renamed after
    known = ["STM32F407VGT6 microcontroller", "100nF 0603 capacitors"]
    made = [{"description": known[i] if i < 2 else d, "quantity": q} for i, (d, q) in enumerate(items)]
    rid = new_request(c, items=made)
    c.post(f"/requests/{rid}/discover")
    assert c.get(f"/requests/{rid}/shortlist").json(), "the demo suppliers should be found"
    for d in c.post(f"/requests/{rid}/rfqs/draft").json():
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    sid = c.get(f"/requests/{rid}/shortlist").json()[0]["supplier_id"]
    o = _offer(c, rid, sid, [price] * len(items), incoterm="DAP", incoterm_place="Belgrade")
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": o["id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"})
    assert po.status_code == 200, po.text
    for row, (label, _q) in zip(
        c.session.query(RequestItem).filter_by(request_id=rid).order_by(RequestItem.id), items, strict=True
    ):
        row.description = label
    c.session.commit()
    row = c.session.get(PurchaseOrder, po.json()["id"])
    if when:
        row.created_at = datetime(when.year, when.month, when.day, 12, tzinfo=UTC)
        c.session.commit()
    return row


def _by_label(data):
    return {r["label"]: r for r in data["rows"]}


def test_no_orders_no_classes(c):
    d = c.get("/analytics/abc-xyz").json()
    assert d["rows"] == [] and d["total_spend_eur"] == 0 and d["orders_used"] == 0
    assert d["xyz_available"] is False and "XYZ needs at least 3" in d["xyz_note"]


def test_abc_is_by_cumulative_spend_and_the_crossing_article_stays_in_the_higher_class(c):
    _ordered(c, [("Big part", 1000)], price=10)
    _ordered(c, [("Middle part", 100)], price=10)
    _ordered(c, [("Small part", 10)], price=10)
    d = c.get("/analytics/abc-xyz").json()
    r = _by_label(d)
    assert [x["label"] for x in d["rows"]] == ["Big part", "Middle part", "Small part"]
    assert (r["Big part"]["abc"], r["Middle part"]["abc"], r["Small part"]["abc"]) == ("A", "B", "C")
    assert r["Big part"]["spend_eur"] == 10000 and d["total_spend_eur"] == 11100
    assert r["Big part"]["share_pct"] == 90.09 and r["Small part"]["cumulative_pct"] == 100
    assert d["matrix"]["A-"]["articles"] == 1 and d["matrix"]["C-"]["spend_eur"] == 100
    assert d["xyz_available"] is False and all(x["xyz"] is None for x in d["rows"])  # one month only


def test_xyz_is_by_the_steadiness_of_the_monthly_quantity(c):
    months = [date(2027, m, 10) for m in range(1, 7)]
    for i, when in enumerate(months):
        items = [("Steady", 10)]
        if i % 2 == 0:
            items.append(("Every other month", 10))
        if i == 0:
            items.append(("One big order", 60))
        _ordered(c, items, when)
    d = abcxyz.analyse(c.session, SETTINGS, today=date(2027, 6, 20))
    r = _by_label(d)
    assert d["xyz_available"] and d["history_months"] == 6
    assert (r["Steady"]["cv"], r["Steady"]["xyz"]) == (0, "X")
    assert (r["Every other month"]["cv"], r["Every other month"]["xyz"]) == (1.0, "Y")
    assert r["One big order"]["xyz"] == "Z" and r["One big order"]["cv"] == pytest.approx(2.236, abs=0.001)
    assert r["Steady"]["orders"] == 6 and r["Steady"]["quantity"] == 60
    assert d["matrix"][r["Steady"]["abc"] + "X"]["articles"] >= 1
    assert r["Steady"]["class"] == r["Steady"]["abc"] + "X"


def test_too_little_history_gives_no_xyz_class(c):
    _ordered(c, [("Only article", 10)], date(2027, 6, 10))
    d = abcxyz.analyse(c.session, SETTINGS, today=date(2027, 6, 20))
    assert d["history_months"] == 1 and d["xyz_available"] is False
    assert d["rows"][0]["xyz"] is None and d["rows"][0]["class"] == "A"
    assert "only 1 month(s)" in d["xyz_note"]


def test_orders_that_cannot_be_split_or_do_not_count_are_set_apart(c):
    ok = _ordered(c, [("Counted", 10)])
    bare = _ordered(c, [("No price lines", 10)])
    c.session.query(OfferLine).filter(OfferLine.offer_id == bare.offer_id).delete()
    gone = _ordered(c, [("Cancelled order", 10)])
    gone.delivery_status = "cancelled"
    old = _ordered(c, [("Too old", 10)], date.today().replace(year=date.today().year - 3))
    c.session.commit()
    d = c.get("/analytics/abc-xyz").json()
    assert [r["label"] for r in d["rows"]] == ["Counted"] and d["orders_used"] == 1
    assert (d["orders_not_itemised"], d["orders_cancelled"], d["orders_before_window"]) == (1, 1, 1)
    assert ok.id and old.id


def test_boundaries_come_from_settings_and_are_checked(c):
    _ordered(c, [("Big part", 1000)], price=10)
    _ordered(c, [("Middle part", 100)], price=10)
    body = {
        "changed_by": "kartel",
        "a_pct": 50,
        "b_pct": 99,
        "x_max": 0.3,
        "y_max": 0.8,
        "window_months": 6,
        "min_months": 2,
    }
    assert c.put("/settings/abcxyz", json={**body, "b_pct": 50}).status_code == 422
    assert c.put("/settings/abcxyz", json={**body, "y_max": 0.3}).status_code == 422
    assert c.put("/settings/abcxyz", json={**body, "a_pct": 100}).status_code == 422
    s = c.put("/settings/abcxyz", json=body).json()["abcxyz"]
    assert s == {"a_pct": 50, "b_pct": 99, "x_max": 0.3, "y_max": 0.8, "window_months": 6, "min_months": 2}
    d = c.get("/analytics/abc-xyz").json()
    assert d["boundaries"]["a_pct"] == 50 and d["window_months"] == 6
    assert _by_label(d)["Middle part"]["abc"] == "B"  # still B: 90% of spend was already used by the first


def test_defaults_are_the_common_starting_values(c):
    s = c.get("/settings").json()["abcxyz"]
    assert s == {"a_pct": 80, "b_pct": 95, "x_max": 0.5, "y_max": 1.0, "window_months": 12, "min_months": 3}


def test_export_is_a_workbook_with_the_table_the_matrix_and_the_basis(c):
    _ordered(c, [("Big part", 1000)], price=10)
    r = c.get("/analytics/abc-xyz.xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["ABC-XYZ", "Matrix", "Basis"]
    rows = list(wb["ABC-XYZ"].iter_rows(values_only=True))
    assert rows[0][0] == "Article" and rows[1][0] == "Big part" and rows[1][3] == 10000 and rows[1][6] == "A"
    basis = dict(wb["Basis"].iter_rows(values_only=True))
    assert basis["A up to cumulative %"] == 80 and "available" not in str(basis["XYZ"])
