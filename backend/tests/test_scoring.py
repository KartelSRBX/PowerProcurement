import pytest

from app.scoring.scoring import (
    OfferFacts,
    SupplierFacts,
    Weights,
    landed_cost,
    score_lead_time,
    score_offers,
    score_price,
    score_reliability,
    score_terms,
)


def sup(**kw) -> SupplierFacts:
    base = dict(
        country="RS",
        age_years=10,
        vat_verified=True,
        deals_count=15,
        framework_contract=True,
        payment_terms_days=60,
        warranty_months=24,
        sanctioned=False,
        flags=[],
    )
    return SupplierFacts(**{**base, **kw})


def offer(i, cost=1000.0, lead=10, covers=True, moq_ok=True) -> OfferFacts:
    return OfferFacts(i, i, cost, lead, covers, moq_ok)


def test_default_weights_are_the_plan_weights_and_sum_to_one():
    w = Weights().normalized()
    assert w == pytest.approx(
        {"price": 0.30, "lead_time": 0.20, "reliability": 0.20, "terms": 0.15, "external_risk": 0.15}
    )
    assert sum(w.values()) == pytest.approx(1.0)


def test_weights_are_renormalised_and_validated():
    assert Weights(1, 1, 1, 1, 0).normalized()["external_risk"] == 0
    with pytest.raises(ValueError):
        Weights(0, 0, 0, 0, 0).normalized()
    with pytest.raises(ValueError):
        Weights(-1, 1, 1, 1, 1).normalized()


def test_price_score_is_100_at_or_below_target_and_falls_above():
    assert score_price(900, 1000) == 100
    assert score_price(1250, 1000) == pytest.approx(80)
    assert score_price(0, 1000) == 0


def test_lead_time_penalises_each_late_day_and_floors_at_zero():
    assert score_lead_time(10, 14) == 100
    assert score_lead_time(16, 14) == 80
    assert score_lead_time(40, 14) == 0
    assert score_lead_time(10, None) == 90


def test_reliability_and_terms_reach_100_for_an_ideal_supplier_and_flags_reduce_it():
    assert score_reliability(sup()) == 100
    flagged = sup(flags=[{"label": "late deliveries", "criterion": "reliability", "penalty": 25}])
    assert score_reliability(flagged) == 75
    assert score_terms(sup(), True) == 100
    assert score_terms(sup(framework_contract=False, payment_terms_days=0, warranty_months=0), False) == 0


def test_landed_cost_uses_country_rate():
    assert landed_cost(1000, "CN") == pytest.approx(1180)
    assert landed_cost(1000, "XX") == pytest.approx(1100)


def test_sanctioned_and_incomplete_offers_are_excluded_with_a_reason_and_ranked_last():
    results = score_offers(
        [(offer(1), sup(sanctioned=True)), (offer(2, covers=False), sup()), (offer(3), sup())],
        target_eur=1000,
        days_available=14,
        weights=Weights(),
    )
    assert [r.offer_id for r in results] == [3, 1, 2]
    assert results[1].excluded == "sanctions list match" and results[2].excluded.startswith("does not cover")


def test_same_inputs_give_same_ranking_and_cheaper_wins_when_all_else_equal():
    inputs = [(offer(1, cost=1200), sup()), (offer(2, cost=1000), sup())]
    a = score_offers(inputs, 1000, 14, Weights())
    b = score_offers(inputs, 1000, 14, Weights())
    assert a == b and a[0].offer_id == 2 and a[0].total > a[1].total


def test_changing_weights_changes_the_winner():
    cheap_slow = (offer(1, cost=1000, lead=40), sup())
    pricey_fast = (offer(2, cost=1300, lead=5), sup())
    price_first = score_offers([cheap_slow, pricey_fast], 1000, 14, Weights(90, 2, 2, 2, 4))
    speed_first = score_offers([cheap_slow, pricey_fast], 1000, 14, Weights(2, 90, 2, 2, 4))
    assert price_first[0].offer_id == 1 and speed_first[0].offer_id == 2


def test_without_a_target_the_cheapest_eligible_offer_is_the_reference():
    r = score_offers([(offer(1, cost=1000), sup()), (offer(2, cost=2000), sup())], None, None, Weights())
    by_id = {x.offer_id: x for x in r}
    assert by_id[1].scores["price"] == 100 and by_id[2].scores["price"] == 50
