"""Fixes from the review before the first release: wording checks, double sends, repeated actions."""

from app.assist.drafts import _check, _has
from tests.test_assist import ai, quote_sent, sent_flow  # noqa: F401
from tests.test_files_orders import with_order
from tests.test_pipeline_e2e import client, new_request  # noqa: F401

BODY = "Dear colleague, please confirm the order below. Thank you for your help. PowerProcurement"


def test_numbers_must_stand_alone():
    assert _has("lead time 15 days", "15")
    assert not _has("lead time 15 days", "5")
    assert not _has("price is 12,500.00 eur", "500.00")
    assert _has("total 1,250.00 eur.", "1,250.00 eur")


def test_check_rejects_amounts_that_were_not_given():
    assert _check("s", BODY + " Total 1,250.00 EUR.", "r", ["1,250.00 EUR"], ["1,250.00 EUR"]) is None
    why = _check("s", BODY + " Total 1,250.00 EUR, or 900.00 EUR for you.", "r", [], ["1,250.00 EUR"])
    assert why and "900.00 EUR" in why
    assert _check("s", BODY + " It costs 10 EUR.", "r", [], [])  # an RFQ states no money at all
    assert _check("s", BODY + " We need 12 pieces in 15 days.", "r", [], []) is None


def test_second_order_for_one_request_is_refused(ai):  # noqa: F811
    c, fake = ai
    rid, q, po = with_order(c, fake)
    again = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"})
    assert again.status_code == 409
    assert len(c.get(f"/requests/{rid}/orders").json()) == 1


def test_discovery_again_keeps_the_suppliers_a_person_unticked(client):  # noqa: F811
    c = client
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    first = [s for s in c.get(f"/requests/{rid}/shortlist").json() if s["selected"]]
    assert len(first) >= 2
    c.post(f"/requests/{rid}/shortlist/{first[0]['supplier_id']}", json={"selected": False})
    c.post(f"/requests/{rid}/discover")
    now = {s["supplier_id"]: s["selected"] for s in c.get(f"/requests/{rid}/shortlist").json()}
    assert now[first[0]["supplier_id"]] is False


def test_no_chasing_for_quotations_once_the_order_is_placed(ai):  # noqa: F811
    c, fake = ai
    rid, q, po = with_order(c, fake)
    assert c.get(f"/requests/{rid}/followups?silent_days=0").json() == []


def test_a_confirmed_answer_cannot_rewrite_the_offer_after_a_quote_exists(ai):  # noqa: F811
    c, fake = ai
    rid, q = quote_sent(c, fake)
    sids = [o["supplier_id"] for o in c.get(f"/requests/{rid}/offers").json()]
    fake.answers["supplier_reply"] = {"confidence": 0.9, "is_offer": True, "lines": []}
    r = c.post(
        f"/requests/{rid}/replies", json={"supplier_id": sids[0], "text": "new price", "entered_by": "kartel"}
    ).json()
    res = c.post(
        f"/replies/{r['id']}/confirm",
        json={"confirmed_by": "kartel", "total_price": 1.0, "currency": "EUR", "lead_time_days": 1},
    )
    assert res.status_code == 409
