"""Hints for the reviewer: what a letter says compared with the plain template, and how long decisions
take. They read recorded text and times; they never block an approval or change a score."""

from datetime import UTC, datetime, timedelta

from app.assist import drafts, review
from app.models import CustomerQuote, Letter, Rfq
from app.rfq.templates import ItemLine, rfq_letter
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import client, new_request  # noqa: F401


def _drafts(c):
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    return rid, c.post(f"/requests/{rid}/rfqs/draft").json()


def _item(c, rfq_id):
    return next(i for i in c.get("/approvals").json() if i["key"] == f"rfq:{rfq_id}")


def test_changes_compares_line_by_line():
    a = "Hello\nWe need 5 pcs\nRegards"
    same = review.changes(a, a + "\n")
    assert same["known"] and not same["changed"] and (same["added"], same["removed"]) == (0, 0)
    edited = review.changes(a, "Hello\nWe need 7 pcs\nRegards")
    assert edited["changed"] and (edited["added"], edited["removed"]) == (1, 1)
    assert [x for x in edited["lines"] if x["op"] != "same"] == [
        {"op": "del", "text": "We need 5 pcs"},
        {"op": "add", "text": "We need 7 pcs"},
    ]
    assert not review.changes(a, "Hello  \r\nWe need 5 pcs\r\nRegards")["changed"]  # only whitespace
    unknown = review.changes(None, a)
    assert unknown["known"] is False and not unknown["changed"] and unknown["lines"] == []


def test_a_draft_carries_the_template_text_and_still_unpacks_as_three(monkeypatch):
    items = [ItemLine(description="Capacitor", quantity=10)]
    monkeypatch.setattr(
        drafts,
        "_ai_letter",
        lambda *a, **k: ("AI subject [PP-00001]", "AI wrote this letter text", "AI · test"),
    )
    d = drafts.rfq_text(None, None, "en", "Acme", items, None, "PP-00001")
    subject, body, by = d
    assert (subject, body, by) == ("AI subject [PP-00001]", "AI wrote this letter text", "AI · test")
    assert d.template == rfq_letter("en", "Acme", items, None, "PP-00001")[1] != body


def test_a_letter_is_stored_with_its_template_and_edits_show_as_changes(client):  # noqa: F811
    c = client
    _rid, ds = _drafts(c)
    first = ds[0]["id"]
    row = c.session.get(Rfq, first)
    assert row.template_body == row.body
    assert _item(c, first)["changes"]["known"] and not _item(c, first)["changes"]["changed"]

    c.patch(f"/rfqs/{first}", json={"body": row.body + "\nPlease quote delivery to Nis."})
    ch = _item(c, first)["changes"]
    assert ch["changed"] and ch["added"] == 1 and ch["removed"] == 0
    assert {"op": "add", "text": "Please quote delivery to Nis."} in ch["lines"]
    assert c.session.get(Rfq, first).template_body == row.template_body  # the template does not move


def test_quotes_and_follow_up_letters_keep_their_template_too(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    o = _offer(c, rid, sids[0], [10, 20], incoterm="DAP", incoterm_place="Belgrade")
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": o["id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    assert c.session.get(CustomerQuote, q["id"]).template_body == q["body"]
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    r = c.post(f"/quotes/{q['id']}/reminder")
    assert r.status_code == 200
    letter = c.session.get(Letter, r.json()["id"])
    assert letter.template_body == letter.body and letter.template_body


def test_review_time_is_the_time_from_draft_to_decision(client):  # noqa: F811
    c = client
    _rid, ds = _drafts(c)
    a, b = ds[0]["id"], ds[1]["id"]
    now = datetime.now(UTC)
    for rfq_id, ago in ((a, 120), (b, 30)):
        c.session.get(Rfq, rfq_id).created_at = now - timedelta(minutes=ago)
    c.session.commit()
    assert c.post(f"/rfqs/{a}/decision", json={"approve": True, "decided_by": "kartel"}).status_code == 200
    assert c.post(f"/rfqs/{b}/decision", json={"approve": False, "decided_by": "kartel"}).status_code == 200
    s = c.get("/approvals/stats").json()
    rfq = next(k for k in s["kinds"] if k["kind"] == "rfq")
    assert (rfq["decided"], rfq["approved"], rfq["rejected"]) == (2, 1, 1)
    assert 74 < rfq["mean_minutes"] < 76 and 74 < rfq["median_minutes"] < 76
    assert 119 < rfq["longest_minutes"] < 121
    assert rfq["compared"] == 2 and rfq["changed"] == 0
    assert s["by_source"]["template"] == {"compared": 2, "changed": 0} and s["decided"] == 2
    assert "waiting" in s["note"]


def test_changed_share_old_decisions_and_the_period(client):  # noqa: F811
    c = client
    _rid, ds = _drafts(c)
    ids = [d["id"] for d in ds[:3]]
    c.patch(f"/rfqs/{ids[0]}", json={"body": "A completely different text of this letter."})
    for i in ids:
        c.post(f"/rfqs/{i}/decision", json={"approve": True, "decided_by": "kartel"})
    s = c.get("/approvals/stats").json()
    assert s["by_source"]["template"] == {"compared": 3, "changed": 1}
    # a decision from before times were recorded has no time and is counted apart
    c.session.get(Rfq, ids[1]).decided_at = None
    # and one older than the period is left out
    c.session.get(Rfq, ids[2]).decided_at = datetime.now(UTC) - timedelta(days=40)
    c.session.commit()
    s = c.get("/approvals/stats?days=30").json()
    assert s["decided"] == 1 and s["decided_without_time"] == 1
    assert c.get("/approvals/stats?days=90").json()["decided"] == 2


def test_an_empty_period_has_no_numbers(client):  # noqa: F811
    s = client.get("/approvals/stats").json()
    assert s["decided"] == 0 and s["kinds"] == [] and s["decided_without_time"] == 0
