"""A saved landed-cost calculation decides an offer's cost in scoring, quote preview, quote and purchase
order; the old flat estimate stays as the fallback and says why it was used."""

import pytest
from pytest import approx as A

from app.models import Offer
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import client  # noqa: F401


def _calc(c, rid, offer, **over):
    """A complete calculation for the offer: CIF carries freight and insurance, so the buyer adds
    inland transport 100 and the agent 50; no duty; VAT 20% is reclaimed. Landed = goods + 150."""
    d = c.get(f"/requests/{rid}/landed-draft", params={"offer_id": offer["id"]}).json()
    body = {
        "currency": d["currency"],
        "incoterm": "CIF",
        "lines": [
            {k: ln[k] for k in ("description", "quantity", "unit_price")} | {"duty_pct": 0}
            for ln in d["lines"]
        ],
        "inland": 100,
        "clearance": 50,
        "vat_pct": 20,
        "saved_by": "kartel",
    }
    return body | over


def _row(c, rid, offer_id):
    return next(r for r in c.post(f"/requests/{rid}/score").json() if r["offer_id"] == offer_id)


def _offers(c):
    rid, sids, _ = _setup(c)
    a = _offer(c, rid, sids[0], [10, 20], incoterm="CIF", incoterm_place="Belgrade")
    b = _offer(c, rid, sids[1], [12, 15], incoterm="CIF", incoterm_place="Belgrade")
    return rid, a, b


def test_without_a_saved_calculation_the_flat_estimate_is_used_and_labelled(client):  # noqa: F811
    rid, a, _ = _offers(client)
    row = _row(client, rid, a["id"])
    assert row["cost_source"] == "flat estimate" and "no calculation saved" in row["cost_note"]


def test_a_complete_saved_calculation_sets_the_cost_in_scoring_preview_quote_and_order(client):  # noqa: F811
    c = client
    rid, a, b = _offers(c)
    goods = a["total_price"]
    flat = _row(c, rid, a["id"])["landed_cost_eur"]
    r = c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a))
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["used"] and saved["complete"] and saved["landed_cost_eur"] == A(goods + 150)
    row = _row(c, rid, a["id"])
    assert row["cost_source"] == "calculation" and row["cost_note"] == ""
    assert row["landed_cost_eur"] == A(goods + 150) and row["landed_cost_eur"] != A(flat)
    assert _row(c, rid, b["id"])["cost_source"] == "flat estimate"  # only the offer that has one

    prev = c.get(
        f"/requests/{rid}/quote-preview", params={"offer_id": a["id"], "markup": 0.2, "currency": "EUR"}
    ).json()
    assert prev["cost_source"] == "calculation" and prev["landed_cost_eur"] == A(goods + 150)
    assert prev["price_eur"] == A((goods + 150) * 1.2)
    assert {ln["key"] for ln in prev["cost_breakdown"]["lines"]} >= {"goods", "inland", "clearance"}

    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": a["id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    assert q["cost_basis"] == "calculation" and q["cost_eur"] == A(goods + 150)
    assert q["cost_breakdown"]["saved_by"] == "kartel"
    assert {ln["key"] for ln in q["cost_breakdown"]["lines"]} >= {"goods", "inland", "clearance"}

    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).json()
    assert po["total_eur"] == A(goods + 150) and po["budget_checks"]["cost_source"] == "calculation"


def test_a_flat_quote_records_that_it_was_flat_and_what_the_estimate_was(client):  # noqa: F811
    c = client
    rid, a, _ = _offers(c)
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": a["id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    assert q["cost_basis"] == "flat estimate" and "no calculation saved" in q["cost_breakdown"]["note"]
    assert {ln["key"] for ln in q["cost_breakdown"]["lines"]} == {"goods", "flat"}
    assert q["cost_breakdown"]["landed_cost_eur"] == A(q["cost_eur"])


def test_an_incomplete_calculation_is_saved_but_not_used(client):  # noqa: F811
    c = client
    rid, a, _ = _offers(c)
    r = c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a, clearance=None))
    assert r.status_code == 200 and r.json()["complete"] is False and r.json()["used"] is False
    row = _row(c, rid, a["id"])
    assert row["cost_source"] == "flat estimate" and "incomplete" in row["cost_note"]
    d = c.get(f"/requests/{rid}/landed-draft", params={"offer_id": a["id"]}).json()
    assert d["saved"]["inputs"]["inland"] == 100 and d["saved"]["used"] is False  # the form can be refilled


def test_a_calculation_for_another_price_is_refused_and_a_changed_offer_drops_it(client):  # noqa: F811
    c = client
    rid, a, _ = _offers(c)
    wrong = _calc(c, rid, a)
    wrong["lines"][0]["unit_price"] *= 2
    r = c.put(f"/offers/{a['id']}/cost", json=wrong)
    assert r.status_code == 422 and "add up to" in r.json()["detail"]
    assert c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a)).status_code == 200
    offer = c.session.get(Offer, a["id"])
    offer.total_price *= 1.5
    c.session.commit()
    row = _row(c, rid, a["id"])
    assert row["cost_source"] == "flat estimate" and "price changed" in row["cost_note"]


def test_saving_needs_a_name_and_a_saved_calculation_can_be_removed(client):  # noqa: F811
    c = client
    rid, a, _ = _offers(c)
    assert c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a, saved_by=" ")).status_code == 422
    assert c.put("/offers/9999/cost", json=_calc(c, rid, a)).status_code == 404
    c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a))
    assert c.delete(f"/offers/{a['id']}/cost").status_code == 200
    assert _row(c, rid, a["id"])["cost_source"] == "flat estimate"
    assert c.delete(f"/offers/{a['id']}/cost").status_code == 404
    assert c.get(f"/requests/{rid}/landed-draft", params={"offer_id": a["id"]}).json()["saved"] is None


def test_saving_again_replaces_the_calculation(client):  # noqa: F811
    c = client
    rid, a, _ = _offers(c)
    c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a))
    again = c.put(f"/offers/{a['id']}/cost", json=_calc(c, rid, a, inland=300, saved_by="anna")).json()
    assert again["landed_cost_eur"] == pytest.approx(a["total_price"] + 350) and again["saved_by"] == "anna"
    assert _row(c, rid, a["id"])["landed_cost_eur"] == A(a["total_price"] + 350)
