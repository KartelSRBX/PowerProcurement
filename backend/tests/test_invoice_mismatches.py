"""The list of invoices that differ from their orders: what differs (total, price, quantity, a missing
item, lines that do not add up, a number the same supplier already used), largest amount first, open ones
by default."""

from app.models import PurchaseOrder
from tests.test_delivery import _po
from tests.test_invoice import _inv, _items, _lines
from tests.test_pipeline_e2e import client  # noqa: F401

URL = "/supplier-invoices/mismatches"


def _three(c):
    """A matches; B is 2,000 over and has a dearer first item; C matches but reuses B's number."""
    a, b, d = _po(c), _po(c), _po(c)
    _inv(c, a, number="A-1", lines=_lines(c, a))
    _inv(c, b, number="INV-2026/7", total_net=47000, lines=_lines(c, b, p=(14, 20)))
    _inv(c, d, number="inv 2026 7", total_net=45000)
    return a, b, d


def test_nothing_differs_nothing_is_listed(client):  # noqa: F811
    c = client
    assert c.get(URL).json() == {
        "show": "open",
        "kind": None,
        "count": 0,
        "by_kind": dict.fromkeys(
            ("total", "price", "quantity", "missing_item", "lines_sum", "foreign_line", "duplicate_number"), 0
        ),
        "rows": [],
    }
    a = _po(c)
    _inv(c, a, lines=_lines(c, a))
    assert c.get(URL).json()["count"] == 0


def test_each_difference_is_listed_with_its_kind_and_the_largest_amount_first(client):  # noqa: F811
    c = client
    a, b, d = _three(c)
    r = c.get(URL).json()
    assert [row["order_id"] for row in r["rows"]] == [b["id"], d["id"]]  # A matches and is not listed
    first = r["rows"][0]
    assert first["kinds"] == ["total", "price", "duplicate_number"]  # the lines add up to 47,000
    assert first["difference"] == 2000 and first["difference_eur"] == 2000
    assert any("+40.00%" in i["text"] for i in first["issues"] if i["kind"] == "price")
    assert r["rows"][1]["kinds"] == ["duplicate_number"]
    assert r["by_kind"] == {
        "total": 1,
        "price": 1,
        "quantity": 0,
        "missing_item": 0,
        "lines_sum": 0,
        "foreign_line": 0,
        "duplicate_number": 2,
    }
    assert r["count"] == 2


def test_a_quantity_and_a_missing_item_are_their_own_kinds(client):  # noqa: F811
    c = client
    po = _po(c)
    first = _items(c, po)[0]["id"]
    _inv(c, po, total_net=4500, lines=[{"item_id": first, "quantity": 450, "unit_price": 10}])
    kinds = c.get(URL).json()["rows"][0]["kinds"]
    assert "quantity" in kinds and "missing_item" in kinds and "total" in kinds


def test_the_same_number_from_another_supplier_is_not_a_duplicate(client):  # noqa: F811
    c = client
    a, b = _po(c), _po(c)
    other = next(s["id"] for s in c.get("/suppliers").json() if s["id"] != a["supplier_id"])
    c.session.get(PurchaseOrder, b["id"]).supplier_id = other
    c.session.commit()
    _inv(c, a, number="INV-9")
    _inv(c, b, number="INV-9")
    assert c.get(URL).json()["count"] == 0


def test_the_filters_and_accepted_invoices(client):  # noqa: F811
    c = client
    a, b, d = _three(c)
    assert [r["order_id"] for r in c.get(URL, params={"kind": "price"}).json()["rows"]] == [b["id"]]
    assert c.get(URL, params={"kind": "duplicate_number"}).json()["count"] == 2
    # accepting one takes it out of the open list and into "accepted"
    ok = c.post(
        f"/orders/{d['id']}/supplier-invoice/accept", json={"by": "kartel", "reason": "same invoice twice"}
    )
    assert ok.status_code == 200
    assert [r["order_id"] for r in c.get(URL).json()["rows"]] == [b["id"]]
    acc = c.get(URL, params={"show": "accepted"}).json()["rows"]
    assert [r["order_id"] for r in acc] == [d["id"]] and acc[0]["accepted_by"] == "kartel"
    assert c.get(URL, params={"show": "all"}).json()["count"] == 2
    assert c.get(URL, params={"kind": "nonsense"}).status_code == 422
    assert c.get(URL, params={"show": "x"}).status_code == 422


def test_the_order_view_shows_the_duplicate_too(client):  # noqa: F811
    c = client
    a, b, d = _three(c)
    cmp = c.get(f"/orders/{d['id']}/supplier-invoice").json()["comparison"]
    assert cmp["status"] == "differs" and f"order #{b['id']}" in cmp["reasons"][0]
