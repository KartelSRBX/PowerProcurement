"""Markup analytics must recover the patterns planted in the synthetic history (plan, phase 7)."""

import statistics

from app.analytics import pricing, synthetic
from app.analytics.pricing import Row
from tests.test_pipeline_e2e import client, new_request, run_to_offers  # noqa: F401


def _rows(seed: int) -> list[Row]:
    return [
        Row(
            h.customer,
            h.category,
            h.cost_eur,
            h.markup,
            h.outcome,
            h.counter_price_eur,
            h.price_eur,
            "synthetic",
        )
        for h in synthetic.generate(seed)
    ]


def test_win_rate_falls_with_markup():
    b = {x["from"]: x for x in pricing.buckets(_rows(7))}
    assert b[0.0]["win_rate"] > b[0.25]["win_rate"] > b[0.4]["win_rate"]
    assert b[0.0]["win_rate"] > 0.8 and b[0.4]["win_rate"] < 0.4


def test_suggested_markup_recovers_each_customers_planted_optimum():
    sens = next(p for p in synthetic.PROFILES if p.midpoint == min(q.midpoint for q in synthetic.PROFILES))
    insens = next(p for p in synthetic.PROFILES if p.midpoint == max(q.midpoint for q in synthetic.PROFILES))
    for seed in (7, 11, 23):
        rows = _rows(seed)
        errors = []
        for p in synthetic.PROFILES:
            s = pricing.suggestion(rows, customer=p.customer, category=p.category)
            assert s["basis"] == "customer"
            errors.append(abs(s["markup"] - synthetic.best_markup(p)))
        assert statistics.mean(errors) < 0.045, (seed, errors)
        low = pricing.suggestion(rows, customer=sens.customer)["markup"]
        high = pricing.suggestion(rows, customer=insens.customer)["markup"]
        assert high - low > 0.12, (seed, low, high)  # planted gap is about 0.21


def test_suggestion_falls_back_when_a_customer_has_too_little_data():
    rows = _rows(7)
    s = pricing.suggestion(rows, customer="new-customer@example.com", category="other")
    assert s["basis"] == "category" and s["markup"] is not None
    assert pricing.suggestion(rows[:5])["markup"] is None  # too few quotes: no suggestion, says so


def test_api_demo_history_and_live_quotes_are_counted(client):  # noqa: F811
    c = client
    assert c.get("/analytics/pricing").json()["summary"]["n"] == 0
    added = c.post("/analytics/demo-history").json()["added"]
    assert added == sum(p.quotes for p in synthetic.PROFILES)
    assert c.post("/analytics/demo-history").json()["added"] == 0
    o = c.get("/analytics/pricing").json()
    assert o["summary"]["n"] == added and len(o["by_customer"]) == len(synthetic.PROFILES)
    assert o["sources"] == {"synthetic": added}
    # a quote made in this system with a recorded outcome joins the same statistics
    rid = new_request(c)
    run_to_offers(c, rid)
    best = next(r for r in c.post(f"/requests/{rid}/score").json() if not r["excluded"])
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.15, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    o = c.get("/analytics/pricing").json()
    assert o["sources"]["live"] == 1 and o["summary"]["n"] == added + 1
    one = c.get(
        "/analytics/pricing", params={"customer": "buyer@customer.example", "category": "electronics"}
    ).json()
    assert one["summary"]["n"] == 1 and one["suggestion"]["basis"] == "category"
    s = c.get("/analytics/markup-suggestion", params={"customer": synthetic.PROFILES[0].customer}).json()
    assert s["basis"] == "customer" and 0 < s["markup"] < 0.3
