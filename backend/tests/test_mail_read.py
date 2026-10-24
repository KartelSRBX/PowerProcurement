"""Attached supplier mail waits on its request until a person has it read; reading is the same as pasting
the answer, and only a person's confirmation makes an offer."""

from app.crm.service import route_incoming
from tests.test_assist import ai  # noqa: F401
from tests.test_mail_routing import _asked, _eml, _supplier_email
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401


def _attached(c, subject_suffix="", body="We offer 5000 EUR, lead time 7 days."):
    rid, rfqs = _asked(c)
    sup = rfqs[0]["supplier_id"]
    mail = _eml(
        _supplier_email(c, sup),
        f"Re: [PP-{rid:05d}]{subject_suffix}",
        f"<read{rid}{subject_suffix}@x>",
        body=body,
    )
    row, _ = route_incoming(c.session, mail, "eml")
    return rid, sup, row


def test_attached_mail_waits_on_its_request_then_is_read_once(client):  # noqa: F811
    c = client
    rid, sup, row = _attached(c)
    waiting = c.get(f"/requests/{rid}/mail").json()
    assert [(m["id"], m["waiting"], m["supplier_id"]) for m in waiting] == [(row.id, True, sup)]
    r = c.post(f"/mail/{row.id}/read", json={"entered_by": "kartel"})
    assert r.status_code == 200 and r.json()["read_by"] == "manual"  # AI is off: the person types the numbers
    assert "5000 EUR" in r.json()["text"] and r.json()["supplier_id"] == sup
    after = c.get(f"/requests/{rid}/mail").json()[0]
    assert after["waiting"] is False and after["reply"]["id"] == r.json()["id"]
    assert c.post(f"/mail/{row.id}/read", json={"entered_by": "kartel"}).status_code == 409  # not twice
    assert c.get(f"/requests/{rid}/offers").json() == []  # reading is not an offer
    offer = c.post(
        f"/replies/{r.json()['id']}/confirm",
        json={"confirmed_by": "kartel", "total_price": 5000, "currency": "EUR", "lead_time_days": 7},
    )
    assert offer.status_code == 200


def test_reading_needs_a_name_an_attached_mail_and_some_text(client):  # noqa: F811
    c = client
    rid, sup, row = _attached(c)
    assert c.post(f"/mail/{row.id}/read", json={"entered_by": " "}).status_code == 409
    assert c.post("/mail/99999/read", json={"entered_by": "kartel"}).status_code == 404
    stray, _ = route_incoming(c.session, _eml("random@nowhere.example", f"[PP-{rid:05d}] hi", "<s@x>"), "eml")
    assert stray.route == "unattached"
    assert c.post(f"/mail/{stray.id}/read", json={"entered_by": "kartel"}).status_code == 409
    _, _, empty = _attached(c, body=" ")
    r = c.post(f"/mail/{empty.id}/read", json={"entered_by": "kartel"})
    assert r.status_code == 409 and "attachment" in r.json()["detail"]


def test_with_ai_on_the_mail_is_read_into_a_proposal(ai):  # noqa: F811
    c, fake = ai
    rid, sup, row = _attached(c)
    fake.answers["supplier_reply"] = {
        "confidence": 0.9,
        "is_offer": True,
        "lines": [{"item": 1, "unit_price": 10, "currency": "EUR", "lead_time_days": 5}],
        "payment_terms": None,
        "missing": [],
        "problems": [],
        "notes": "",
    }
    r = c.post(f"/mail/{row.id}/read", json={"entered_by": "kartel"}).json()
    assert r["ai"]["used"] and r["proposal"]["total_price"] == 5000.0
    sent_text = fake.calls[-1][1]["text"]
    assert sent_text.startswith("Subject: Re: [PP-") and "5000 EUR" in sent_text


def test_mail_of_other_requests_is_not_listed(client):  # noqa: F811
    c = client
    rid, _, row = _attached(c)
    rid2, _, row2 = _attached(c, subject_suffix=" two")
    assert [m["id"] for m in c.get(f"/requests/{rid}/mail").json()] == [row.id]
    assert [m["id"] for m in c.get(f"/requests/{rid2}/mail").json()] == [row2.id]
