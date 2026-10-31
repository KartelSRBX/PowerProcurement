"""Article signals: a unit price well above the last one paid or ordered for the same article, and a lead time
well above the last order's, with thresholds from Settings. History is this company's own orders only."""

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from tests.test_comparison import _offer, _setup
from tests.test_delivery import _po
from tests.test_invoice import _inv, _items, _lines
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401
from tests.test_supplier_performance import _order


def _new_offer(c, prices, **over):
    rid, sids, _ = _setup(c)
    o = _offer(c, rid, sids[0], prices, **over)
    return rid, o


def _signals(c, rid):
    r = c.get(f"/requests/{rid}/signals")
    assert r.status_code == 200, r.text
    return r.json()


def test_without_any_earlier_order_there_is_nothing_to_compare(client):  # noqa: F811
    c = client
    rid, o = _new_offer(c, [12, 20])
    s = _signals(c, rid)["offers"][0]
    assert s["signals"] == [] and s["with_history"] == 0 and s["items"][0]["last"] is None


def test_a_price_rise_over_the_threshold_against_the_last_ordered_price_is_flagged(client):  # noqa: F811
    c = client
    _po(c)  # ordered at 10 and 20 per unit
    rid, o = _new_offer(c, [12, 20])
    s = _signals(c, rid)["offers"][0]
    first, second = s["items"]
    assert (
        first["price_change_pct"] == 20.0
        and first["price_signal"]
        and first["last"]["price_kind"] == "ordered"
    )
    assert second["price_change_pct"] == 0.0 and not second["price_signal"]
    assert len(s["signals"]) == 1 and "+20.0% against 10 EUR last ordered" in s["signals"][0]
    # the same text comes with the score table, and the score itself is untouched
    row = c.post(f"/requests/{rid}/score").json()[0]
    assert row["signals"] == s["signals"]


def test_a_paid_price_beats_the_ordered_price(client):  # noqa: F811
    c = client
    po = _po(c)
    _inv(c, po, total_net=46000, lines=_lines(c, po, p=(10.5, 20.25)))  # 500 x 10.5 + 2000 x 20.25 = 45,750
    c.post(f"/orders/{po['id']}/supplier-invoice/accept", json={"by": "kartel", "reason": "agreed"})
    rid, o = _new_offer(c, [12, 20])
    first = _signals(c, rid)["offers"][0]["items"][0]
    assert first["last"]["price_kind"] == "paid" and first["last"]["unit_price_eur"] == 10.5
    assert first["price_change_pct"] == 14.29  # (12 - 10.5) / 10.5


def test_an_invoice_nobody_accepted_is_not_a_paid_price(client):  # noqa: F811
    c = client
    po = _po(c)
    _inv(c, po, total_net=46000, lines=_lines(c, po, p=(10.5, 20.25)))
    rid, o = _new_offer(c, [12, 20])
    assert _signals(c, rid)["offers"][0]["items"][0]["last"]["price_kind"] == "ordered"


def test_the_threshold_is_a_setting_a_named_person_changes(client):  # noqa: F811
    c = client
    _po(c)
    rid, o = _new_offer(c, [12, 20])
    assert _signals(c, rid)["offers"][0]["signals"]  # +20% against the default 10%
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    try:
        body = {"changed_by": "kartel", "price_rise_pct": 25, "lead_rise_pct": 25, "lead_rise_days": 3}
        r = c.put("/settings/signals", json=body)
        assert r.status_code == 200 and r.json()["signals"]["price_rise_pct"] == 25
        s = _signals(c, rid)
        assert s["thresholds"]["price_rise_pct"] == 25 and s["offers"][0]["signals"] == []
        assert c.put("/settings/signals", json={**body, "changed_by": " "}).status_code == 422
        assert c.put("/settings/signals", json={**body, "price_rise_pct": -1}).status_code == 422
    finally:
        set_overrides({})


def test_a_longer_lead_time_than_the_last_delivery_is_flagged_only_past_both_limits(client):  # noqa: F811
    c = client
    sid = c.get("/suppliers").json()[0]["id"]
    _order(c, sid, "2026-01-01", "2026-01-11", "2026-01-11", "2026-01-11")  # delivered after 10 days
    # 12 days: +2 days is under the 3-day floor; 13 days: +3 days and +30%; 11: +10% only
    for days, flagged in ((12, False), (13, True), (11, False), (20, True)):
        rid, o = _new_offer(c, [10, 20], lead_time_days=days)
        lead = _signals(c, rid)["offers"][0]["lead"]
        assert lead["last_days"] == 10 and lead["last_kind"] == "actual", days
        assert lead["signal"] is flagged, days
    assert lead["change_days"] == 10 and lead["change_pct"] == 100.0


def test_the_part_number_identifies_an_article_across_descriptions(client):  # noqa: F811
    c = client
    po = _po(c)
    from app.models import RequestItem

    first = c.session.get(RequestItem, _items(c, po)[0]["id"])
    first.part_number = "STM32F407-VGT6"
    c.session.commit()
    rid, o = _new_offer(c, [12, 20])
    item = c.session.get(RequestItem, _items(c, {"request_id": rid})[0]["id"])
    item.description = "Microcontroller, a different wording"
    item.part_number = "stm32f407 vgt6"
    c.session.commit()
    s = _signals(c, rid)["offers"][0]["items"][0]
    assert s["last"] is not None and s["price_signal"]


def test_a_newer_order_without_a_price_does_not_hide_an_older_price(client):  # noqa: F811
    from app.models import OfferLine, PurchaseOrder

    c = client
    first = _po(c)
    later = _po(c)  # same articles, but its offer has only a total: no unit prices
    offer_id = c.session.get(PurchaseOrder, later["id"]).offer_id
    c.session.query(OfferLine).filter_by(offer_id=offer_id).delete()
    c.session.commit()
    rid, o = _new_offer(c, [12, 20])
    item = _signals(c, rid)["offers"][0]["items"][0]
    assert item["last"]["order_id"] == first["id"] and item["price_signal"]
