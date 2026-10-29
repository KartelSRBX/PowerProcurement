"""Delivery history as a scoring criterion: off by default, weighted from Settings, and used for a supplier
only when it has enough delivered orders with a promised date."""

from dataclasses import replace

import pytest

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from app.scoring.scoring import Weights, score_delivery_history, score_offers
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401
from tests.test_scoring import offer, sup
from tests.test_supplier_performance import _order


def test_the_score_is_the_share_on_time_averaged_over_the_two_dates():
    assert score_delivery_history(75.0, 50.0) == 62.5
    assert score_delivery_history(100.0, None) == 100.0
    assert score_delivery_history(None, None) is None


def _pair(score, note=None):
    return replace(sup(), delivery_score=score, delivery_note=note)


def test_with_no_weight_the_record_changes_nothing():
    plain = score_offers([(offer(1), sup())], 1000, 14, Weights())[0]
    good = score_offers([(offer(1), _pair(100.0))], 1000, 14, Weights())[0]
    assert good.total == plain.total and "delivery_history" not in good.scores


def test_a_weighted_record_moves_the_total_by_the_hand_calculated_amount():
    # same offer, same supplier facts: the five other criteria give B; weights are 100 + 20, so the
    # total is (100 * B + 20 * delivery) / 120
    base = score_offers([(offer(1), sup())], 1000, 14, Weights())[0]
    b = base.total
    w = Weights(delivery_history=20)
    best = score_offers([(offer(1), _pair(100.0))], 1000, 14, w)[0]
    worst = score_offers([(offer(1), _pair(0.0))], 1000, 14, w)[0]
    assert best.scores["delivery_history"] == 100.0
    assert best.total == pytest.approx((100 * b + 20 * 100) / 120, abs=0.01)
    assert worst.total == pytest.approx((100 * b) / 120, abs=0.01)
    assert best.total > worst.total


def test_a_supplier_without_enough_history_is_scored_on_the_other_criteria_and_told_so():
    base = score_offers([(offer(1), sup())], 1000, 14, Weights())[0]
    r = score_offers(
        [(offer(1), _pair(None, "delivery history not used: 1 delivered order(s)"))],
        1000,
        14,
        Weights(delivery_history=20),
    )[0]
    assert r.total == base.total and "delivery_history" not in r.scores
    assert any("delivery history not used" in n for n in r.notes)


# ---- through the API ---------------------------------------------------------------------------


def _use_saved_settings(c):
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))


def test_the_weight_and_the_minimum_are_saved_by_a_named_person_within_limits(client):  # noqa: F811
    c = client
    _use_saved_settings(c)
    try:
        body = {"changed_by": "kartel", "delivery_history_weight": 20, "delivery_history_min_orders": 4}
        assert c.put("/settings/scoring", json={**body, "changed_by": " "}).status_code == 422
        assert c.put("/settings/scoring", json={**body, "delivery_history_weight": 101}).status_code == 422
        assert c.put("/settings/scoring", json={**body, "delivery_history_min_orders": 1}).status_code == 422
        r = c.put("/settings/scoring", json=body)
        assert r.status_code == 200
        assert r.json()["scoring"] == {"delivery_history_weight": 20, "delivery_history_min_orders": 4}
        assert c.get("/settings").json()["scoring"]["delivery_history_weight"] == 20
    finally:
        set_overrides({})


def _scored(c, rid, **weights):
    r = c.post(f"/requests/{rid}/score", json=weights)
    assert r.status_code == 200, r.text
    return {row["supplier"]: row for row in r.json()}


def test_scoring_uses_the_record_only_with_the_minimum_number_of_orders(client):  # noqa: F811
    c = client
    _use_saved_settings(c)
    try:
        rid, sids, _ = _setup(c)
        _offer(c, rid, sids[0], [10, 20])
        _offer(c, rid, sids[1], [10, 20])
        names = {s["id"]: s["name"] for s in c.get("/suppliers").json()}
        good, poor = names[sids[0]], names[sids[1]]
        # supplier 0: three orders, all on time; supplier 1: three orders, all late
        for _ in range(3):
            _order(c, sids[0], "2026-01-01", "2026-01-11", "2026-01-11", "2026-01-10")
            _order(c, sids[1], "2026-01-01", "2026-01-11", "2026-01-11", "2026-01-20")

        # weight 0 (the default): no delivery criterion at all
        off = _scored(c, rid)
        assert all("delivery_history" not in r["scores"] for r in off.values())

        c.put(
            "/settings/scoring",
            json={"changed_by": "kartel", "delivery_history_weight": 30, "delivery_history_min_orders": 3},
        )
        on = _scored(c, rid)
        assert on[good]["scores"]["delivery_history"] == 100.0
        assert on[poor]["scores"]["delivery_history"] == 0.0
        assert on[good]["total"] > on[poor]["total"]

        # raising the minimum above what they have leaves the weight out, with the reason
        c.put(
            "/settings/scoring",
            json={"changed_by": "kartel", "delivery_history_weight": 30, "delivery_history_min_orders": 4},
        )
        few = _scored(c, rid)
        assert all("delivery_history" not in r["scores"] for r in few.values())
        assert all(any("at least 4 needed" in f for f in r["flags"]) for r in few.values())
        assert few[good]["total"] == off[good]["total"]
    finally:
        set_overrides({})
