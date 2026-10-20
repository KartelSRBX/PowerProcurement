"""Offer terms that make offers comparable: validity date, Incoterms rule and place, payment days."""

from datetime import date, timedelta

from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401


def _asked(c):
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    for d in c.post(f"/requests/{rid}/rfqs/draft").json():
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    return rid, c.get(f"/requests/{rid}/shortlist").json()


def _offer(**over):
    return {"total_price": 1000, "currency": "EUR", "lead_time_days": 10, **over}


def test_terms_are_stored_and_shown_in_the_ranking(client):  # noqa: F811
    c = client
    rid, short = _asked(c)
    sid = short[0]["supplier_id"]
    until = (date.today() + timedelta(days=30)).isoformat()
    o = c.post(
        f"/requests/{rid}/offers",
        json=_offer(
            supplier_id=sid, valid_until=until, incoterm="dap", incoterm_place="Belgrade", payment_days=30
        ),
    ).json()
    assert (o["valid_until"], o["incoterm"], o["incoterm_place"], o["payment_days"]) == (
        until,
        "DAP",
        "Belgrade",
        30,
    )
    row = next(r for r in c.post(f"/requests/{rid}/score", json={}).json() if r["offer_id"] == o["id"])
    assert row["incoterm"] == "DAP" and row["payment_days"] == 30 and row["term_flags"] == []


def test_missing_and_expired_terms_are_flagged_not_hidden(client):  # noqa: F811
    c = client
    rid, short = _asked(c)
    bare = c.post(f"/requests/{rid}/offers", json=_offer(supplier_id=short[0]["supplier_id"])).json()
    old = (date.today() - timedelta(days=2)).isoformat()
    stale = c.post(
        f"/requests/{rid}/offers",
        json=_offer(supplier_id=short[1]["supplier_id"], valid_until=old, incoterm="FOB"),
    ).json()
    rows = {r["offer_id"]: r for r in c.post(f"/requests/{rid}/score", json={}).json()}
    assert any("no validity date" in f for f in rows[bare["id"]]["term_flags"])
    assert any("no Incoterms rule" in f for f in rows[bare["id"]]["term_flags"])
    assert any("expired" in f for f in rows[stale["id"]]["term_flags"])
    assert any("needs a named place" in f for f in rows[stale["id"]]["term_flags"])


def test_bad_terms_are_refused(client):  # noqa: F811
    c = client
    rid, short = _asked(c)
    sid = short[0]["supplier_id"]
    for bad in (
        {"incoterm": "XYZ"},
        {"incoterm_place": "Belgrade"},
        {"payment_days": -1},
        {"payment_days": 400},
    ):
        r = c.post(f"/requests/{rid}/offers", json=_offer(supplier_id=sid, **bad))
        assert r.status_code in (400, 409, 422), bad
    assert c.get(f"/requests/{rid}/offers").json() == []


def test_confirming_a_reply_carries_the_terms_and_a_later_answer_replaces_them(client):  # noqa: F811
    c = client
    rid, short = _asked(c)
    sid = short[0]["supplier_id"]
    r = c.post(
        f"/requests/{rid}/replies",
        json={"supplier_id": sid, "text": "5000 EUR, 7 days", "entered_by": "kartel"},
    ).json()
    o = c.post(
        f"/replies/{r['id']}/confirm",
        json={
            "confirmed_by": "kartel",
            **_offer(total_price=5000),
            "incoterm": "EXW",
            "incoterm_place": "Novi Sad",
            "payment_days": 14,
        },
    ).json()
    assert (o["incoterm"], o["incoterm_place"], o["payment_days"]) == ("EXW", "Novi Sad", 14)
    r2 = c.post(
        f"/requests/{rid}/replies", json={"supplier_id": sid, "text": "now 4800 EUR", "entered_by": "kartel"}
    ).json()
    o2 = c.post(
        f"/replies/{r2['id']}/confirm",
        json={
            "confirmed_by": "kartel",
            **_offer(total_price=4800),
            "incoterm": "DAP",
            "incoterm_place": "Belgrade",
        },
    ).json()
    assert o2["id"] == o["id"] and o2["incoterm"] == "DAP" and o2["payment_days"] is None
