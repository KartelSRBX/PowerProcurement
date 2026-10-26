"""The landed-cost calculator for a whole order: shared costs split by value, a breakdown per item, the draft
taken from a request and its offers. Every number is recalculated by hand in the comment above it."""

from pytest import approx as A

from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import client, new_request  # noqa: F401


def _body(**over):
    body = {
        "currency": "EUR",
        "incoterm": "FOB",
        "lines": [
            {"description": "A", "quantity": 10, "unit_price": 60, "duty_pct": 10},
            {"description": "B", "quantity": 5, "unit_price": 80, "duty_pct": 0},
        ],
        "freight": 100,
        "insurance": 20,
        "inland": 50,
        "clearance": 30,
        "vat_pct": 20,
    }
    return body | over


def test_shared_costs_are_split_by_value_and_each_item_has_its_own_breakdown(client):  # noqa: F811
    r = client.post("/pricing/landed", json=_body())
    assert r.status_code == 200, r.text
    d = r.json()
    a, b = d["lines"]
    # values 600 and 400 -> shares 60% and 40%
    # A: freight 60, insurance 12, customs value 672, duty 67.2, base 672+67.2+18+30 = 787.2, VAT 157.44
    assert a["share_pct"] == 60 and a["result"]["customs_value_eur"] == A(672)
    assert a["result"]["duty_eur"] == A(67.2) and a["result"]["landed_cost_eur"] == A(787.2)
    assert a["result"]["vat_eur"] == A(157.44) and a["landed_per_unit_eur"] == A(78.72)
    # B: freight 40, insurance 8, customs value 448, no duty, base 448+12+20 = 480, VAT 96
    assert b["result"]["customs_value_eur"] == A(448) and b["result"]["landed_cost_eur"] == A(480)
    assert b["result"]["vat_eur"] == A(96) and b["landed_per_unit_eur"] == A(96)
    t = d["total"]
    assert t["customs_value_eur"] == A(1120) and t["duty_eur"] == A(67.2)
    assert t["landed_cost_eur"] == A(1267.2) and t["vat_eur"] == A(253.44) and t["cash_out_eur"] == A(1520.64)
    assert d["complete"] and not d["warnings"]
    by_key = {ln["key"]: ln["amount_eur"] for ln in t["lines"]}
    assert by_key["goods"] == 1000 and by_key["carriage"] == 100 and by_key["insurance"] == 20
    assert all(ln["note"] == "" for ln in t["lines"])  # a note about one item's figures is not the sum's
    assert any(ln["note"] for ln in a["result"]["lines"])


def test_amounts_in_another_currency_are_brought_to_eur_at_the_settings_rate(client):  # noqa: F811
    # 11700 RSD at 117 per EUR = 100 EUR; inland 1170 RSD = 10 EUR; CIF has carriage and insurance in it
    # landed 100+10 = 110, VAT 20% of 110 = 22, cash 132
    body = {
        "currency": "RSD",
        "incoterm": "CIF",
        "lines": [{"description": "A", "quantity": 1, "unit_price": 11700, "duty_pct": 0}],
        "inland": 1170,
        "clearance": 0,
        "vat_pct": 20,
    }
    d = client.post("/pricing/landed", json=body).json()
    assert d["total"]["landed_cost_eur"] == A(110) and d["total"]["cash_out_eur"] == A(132)
    assert d["fx"]["RSD"] == 117


def test_a_warning_that_only_one_item_has_names_that_item(client):  # noqa: F811
    body = _body(freight=None)
    body["lines"][1]["duty_pct"] = None
    d = client.post("/pricing/landed", json=body).json()
    assert not d["complete"] and not d["total"]["complete"]
    carriage = [w for w in d["warnings"] if "main carriage" in w]
    assert len(carriage) == 1 and not carriage[0].startswith(("A:", "B:"))  # every item lacks it: said once
    duty = [w for w in d["warnings"] if "duty rate" in w]
    assert len(duty) == 1 and duty[0].startswith("B: ")


def test_bad_input_is_refused_not_guessed(client):  # noqa: F811
    for over in (
        {"currency": "GBP"},
        {"incoterm": "XYZ"},
        {"lines": []},
        {"freight": -1},
        {"vat_pct": -5},
        {"lines": [{"description": "A", "quantity": 0, "unit_price": 5}]},
        {"lines": [{"description": "A", "quantity": 1, "unit_price": 0}]},
    ):
        assert client.post("/pricing/landed", json=_body(**over)).status_code == 422, over


def test_the_draft_lists_the_items_and_takes_prices_incoterms_and_country_from_the_offer(client):  # noqa: F811
    c = client
    rid, sids, items = _setup(c)
    bare = c.get(f"/requests/{rid}/landed-draft").json()
    assert [r["description"] for r in bare["lines"]] == [i["description"] for i in items]
    assert all(r["unit_price"] is None for r in bare["lines"]) and bare["offers"] == []
    offer = _offer(c, rid, sids[0], [10, 20], incoterm="FOB", incoterm_place="Shanghai")
    d = c.get(f"/requests/{rid}/landed-draft", params={"offer_id": offer["id"]}).json()
    assert d["incoterm"] == "FOB" and d["currency"] == "EUR" and d["offer_id"] == offer["id"]
    assert [r["unit_price"] for r in d["lines"]] == [10, 20] and not d["notes"]
    assert len(d["origin_country"]) == 2 and d["offers"][0]["id"] == offer["id"]
    # the draft is a start: its lines go straight into the calculation
    lines = [{k: r[k] for k in ("description", "quantity", "unit_price")} for r in d["lines"]]
    ok = c.post(
        "/pricing/landed", json={"currency": d["currency"], "incoterm": d["incoterm"], "lines": lines}
    )
    assert ok.status_code == 200 and not ok.json()["complete"]  # nothing was typed for freight, duty, VAT


def test_an_offer_with_only_a_total_is_calculated_as_one_item_and_a_missing_rule_is_flagged(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    c.post(
        f"/requests/{rid}/offers",
        json={"supplier_id": sids[0], "total_price": 500, "currency": "EUR", "lead_time_days": 3},
    )
    oid = c.get(f"/requests/{rid}/landed-draft").json()["offers"][0]["id"]
    d = c.get(f"/requests/{rid}/landed-draft", params={"offer_id": oid}).json()
    assert len(d["lines"]) == 1 and d["lines"][0]["unit_price"] == 500 and d["lines"][0]["quantity"] == 1
    assert any("only a total price" in n for n in d["notes"]) and any(
        "no Incoterms rule" in n for n in d["notes"]
    )


def test_an_offer_from_another_request_is_not_found(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    assert c.get(f"/requests/{rid}/landed-draft", params={"offer_id": 9999}).status_code == 404
    assert c.get("/requests/9999/landed-draft").status_code == 404
