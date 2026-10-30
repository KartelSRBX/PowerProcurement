"""A supplier invoice entered on an order, compared with the offer behind it, with a tolerance from Settings
and an acceptance by a named person. Prices come from tests.test_delivery._po: 10 and 20 per unit for 500 and
2000 pieces, so the order is 5,000 + 40,000 = 45,000 EUR."""

from datetime import date

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from app.models import AuditLog
from tests.test_delivery import _po
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401


def _items(c, po):
    return c.get(f"/requests/{po['request_id']}/items").json()


def _inv(c, po, **over):
    body = {
        "entered_by": "kartel",
        "number": "INV-1",
        "invoice_date": date.today().isoformat(),
        "currency": "EUR",
        "total_net": 45000,
        **over,
    }
    return c.put(f"/orders/{po['id']}/supplier-invoice", json=body)


def _lines(c, po, q=(500, 2000), p=(10, 20)):
    return [
        {"item_id": i["id"], "quantity": a, "unit_price": b}
        for i, a, b in zip(_items(c, po), q, p, strict=True)
    ]


def test_an_order_has_no_invoice_until_one_is_entered(client):  # noqa: F811
    po = _po(client)
    r = client.get(f"/orders/{po['id']}/supplier-invoice").json()
    assert r["invoice"] is None and r["comparison"] is None


def test_an_invoice_equal_to_the_order_matches(client):  # noqa: F811
    c = client
    po = _po(c)
    r = _inv(c, po, lines=_lines(c, po))
    assert r.status_code == 200, r.text
    cmp = r.json()["comparison"]
    assert cmp["status"] == "matches" and cmp["reasons"] == []
    assert cmp["ordered_total"] == 45000 and cmp["invoiced_total"] == 45000 and cmp["difference"] == 0
    assert all(ln["quantity_ok"] and ln["price_ok"] for ln in cmp["lines"])


def test_the_tolerance_decides_what_a_difference_is(client):  # noqa: F811
    c = client
    po = _po(c)
    # 45,300 is 0.67% over 45,000: inside the default 1%
    assert _inv(c, po, total_net=45300).json()["comparison"]["status"] == "matches"
    # 45,900 is exactly 2% over
    cmp = _inv(c, po, total_net=45900).json()["comparison"]
    assert cmp["status"] == "differs" and cmp["difference"] == 900 and cmp["difference_pct"] == 2.0
    assert "900.00 EUR more than the order" in cmp["reasons"][0]
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    try:
        r = c.put("/settings/invoices", json={"changed_by": "kartel", "tolerance_pct": 2.5})
        assert r.status_code == 200 and r.json()["invoices"]["tolerance_pct"] == 2.5
        assert c.get(f"/orders/{po['id']}/supplier-invoice").json()["comparison"]["status"] == "matches"
        assert (
            c.put("/settings/invoices", json={"changed_by": "kartel", "tolerance_pct": 50}).status_code == 422
        )
        assert c.put("/settings/invoices", json={"changed_by": " ", "tolerance_pct": 1}).status_code == 422
    finally:
        set_overrides({})


def test_lines_are_compared_on_quantity_exactly_and_on_price_within_the_tolerance(client):  # noqa: F811
    c = client
    po = _po(c)
    # 450 pieces at 10.50 and the second item missing: the total equals the lines, so only they differ
    first = _items(c, po)[0]["id"]
    lines = [{"item_id": first, "quantity": 450, "unit_price": 10.5}]
    cmp = _inv(c, po, total_net=4725, lines=lines).json()["comparison"]
    assert cmp["status"] == "differs"
    text = " | ".join(cmp["reasons"])
    assert "450 invoiced, 500 ordered" in text and "+5.00%" in text and "is not on the invoice" in text
    row = cmp["lines"][0]
    assert row["quantity_ok"] is False and row["price_ok"] is False and row["price_pct"] == 5.0
    assert cmp["lines"][1]["invoiced_quantity"] is None


def test_lines_that_do_not_add_up_to_the_total_are_flagged(client):  # noqa: F811
    c = client
    po = _po(c)
    cmp = _inv(c, po, total_net=45000, lines=_lines(c, po, p=(10, 19))).json()["comparison"]
    assert any("lines add up to 43,000.00 EUR" in r for r in cmp["reasons"])


def test_another_currency_is_compared_in_eur_and_said_so(client):  # noqa: F811
    c = client
    po = _po(c)
    cmp = _inv(c, po, currency="USD", total_net=round(45000 * SETTINGS.fx_usd_per_eur, 2)).json()[
        "comparison"
    ]
    # the currency is a note, not a difference: the same money in another currency matches
    assert cmp["compared_in"] == "EUR" and cmp["status"] == "matches"
    assert any("compared in EUR" in n for n in cmp["notes"])
    assert abs(cmp["difference"]) < 1


def test_bad_input_is_refused(client):  # noqa: F811
    c = client
    po = _po(c)
    assert _inv(c, po, entered_by=" ").status_code == 409
    assert _inv(c, po, number="  ").status_code == 422
    assert _inv(c, po, total_net=0).status_code == 422
    assert _inv(c, po, currency="EU").status_code == 422
    assert _inv(c, po, invoice_date="2999-01-01").status_code == 409
    assert _inv(c, po, lines=[{"item_id": 99999, "quantity": 1, "unit_price": 1}]).status_code == 422
    first = _items(c, po)[0]["id"]
    twice = [{"item_id": first, "quantity": 1, "unit_price": 1}] * 2
    assert _inv(c, po, lines=twice).status_code == 422
    assert c.get("/orders/999/supplier-invoice").status_code == 404


def test_entering_again_replaces_until_it_is_accepted(client):  # noqa: F811
    c = client
    po = _po(c)
    _inv(c, po, number="INV-1", total_net=46000)
    r = _inv(c, po, number="INV-2", total_net=45000)
    assert r.json()["invoice"]["number"] == "INV-2" and r.json()["comparison"]["status"] == "matches"
    assert c.post(f"/orders/{po['id']}/supplier-invoice/accept", json={"by": "kartel"}).status_code == 200
    assert _inv(c, po, number="INV-3").status_code == 409
    assert (
        c.delete(f"/orders/{po['id']}/supplier-invoice", params={"removed_by": "kartel"}).status_code == 409
    )


def test_a_differing_invoice_is_accepted_only_with_a_reason_and_a_name(client):  # noqa: F811
    c = client
    po = _po(c)
    _inv(c, po, total_net=47000)
    url = f"/orders/{po['id']}/supplier-invoice/accept"
    assert c.post(url, json={"by": " ", "reason": "agreed"}).status_code == 409
    assert c.post(url, json={"by": "kartel"}).status_code == 409
    r = c.post(url, json={"by": "kartel", "reason": "freight added, agreed by phone"})
    inv = r.json()["invoice"]
    assert r.status_code == 200 and inv["accepted_by"] == "kartel" and "freight" in inv["accept_reason"]
    assert c.post(url, json={"by": "kartel"}).status_code == 409  # already accepted
    entry = c.session.query(AuditLog).filter_by(action="invoice.accepted").one()
    assert entry.actor_id == "kartel" and entry.payload["status"] == "differs"


def test_removing_an_open_invoice_clears_it(client):  # noqa: F811
    c = client
    po = _po(c)
    _inv(c, po)
    r = c.delete(f"/orders/{po['id']}/supplier-invoice", params={"removed_by": "kartel"})
    assert r.status_code == 200 and r.json()["invoice"] is None
    assert (
        c.delete(f"/orders/{po['id']}/supplier-invoice", params={"removed_by": "kartel"}).status_code == 404
    )


def test_a_cancelled_order_takes_no_invoice(client):  # noqa: F811
    c = client
    po = _po(c)
    c.put(f"/orders/{po['id']}/delivery", json={"changed_by": "kartel", "status": "cancelled"})
    assert _inv(c, po).status_code == 409
