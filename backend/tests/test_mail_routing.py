"""Supplier answers find their request: by the letter's Message-ID, by the request number plus sender,
by the sender alone when only one request waits, and otherwise they wait in the unattached list."""

from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from app.crm.service import route_incoming, unattached_mail
from app.intake.mailbox import EmlDirReader, parse_message
from app.models import InboxEmail
from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401


def _asked(c, how_many=2):
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    for d in c.post(f"/requests/{rid}/rfqs/draft").json():
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    rfqs = c.get(f"/requests/{rid}/rfqs").json()
    assert len(rfqs) >= how_many
    return rid, rfqs


def _eml(sender, subject, mid, in_reply_to="", references="", body="We offer 5000 EUR, 7 days."):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = sender, "sales@us.example", subject, mid
    msg["Date"] = format_datetime(datetime(2026, 10, 23, 9, 0, tzinfo=UTC))
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    return parse_message(msg.as_bytes())


def _supplier_email(c, supplier_id):
    return c.get(f"/suppliers/{supplier_id}").json()["email"]


def test_outgoing_rfq_carries_a_message_id_a_reply_can_point_at(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    ids = {m["message_id"] for m in c.outbox}
    assert all(i and i.startswith("<pp-rfq-") for i in ids) and len(ids) == len(c.outbox)


def test_reply_headers_attach_the_mail_even_from_another_address(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    rfq = rfqs[0]
    mail = _eml(
        "colleague@elsewhere.example",
        "Re: your question",
        "<r1@x>",
        in_reply_to=f"<pp-rfq-{rfq['id']}@powerprocurement.local>",
    )
    row, route = route_incoming(c.session, mail, "eml")
    assert route.kind == "supplier" and (row.route_request_id, row.route_supplier_id) == (
        rid,
        rfq["supplier_id"],
    )
    assert "headers" in row.route_reason


def test_request_number_in_the_subject_needs_the_sender_to_be_a_supplier_asked(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    asked_email = _supplier_email(c, rfqs[0]["supplier_id"])
    ok, r1 = route_incoming(
        c.session, _eml(asked_email, f"Re: Request for quotation [PP-{rid:05d}]", "<r2@x>"), "eml"
    )
    assert r1.kind == "supplier" and ok.route_supplier_id == rfqs[0]["supplier_id"]
    stranger, r2 = route_incoming(
        c.session, _eml("random@nowhere.example", f"RE: [PP-{rid:05d}] price", "<r3@x>"), "eml"
    )
    assert (
        r2.kind == "unattached" and stranger.route_request_id == rid and "not a supplier asked" in r2.reason
    )
    ghost, r3 = route_incoming(c.session, _eml(asked_email, "Re: [PP-99999] price", "<r4@x>"), "eml")
    assert r3.kind == "unattached" and "no letter for it was sent" in r3.reason


def test_known_supplier_without_a_number_attaches_only_when_one_request_waits(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    asked_email = _supplier_email(c, rfqs[0]["supplier_id"])
    row, r = route_incoming(c.session, _eml(asked_email, "Our prices", "<r5@x>"), "eml")
    assert r.kind == "supplier" and row.route_request_id == rid
    rid2, _ = _asked(c)  # now two requests wait for the same supplier
    row2, r2 = route_incoming(c.session, _eml(asked_email, "Our prices", "<r6@x>"), "eml")
    assert r2.kind == "unattached" and "requests waiting" in r2.reason and rid2 != rid


def test_unknown_sender_without_a_number_stays_a_customer_mail(client):  # noqa: F811
    row, r = route_incoming(client.session, _eml("buyer@customer.example", "RFQ: 500 pcs", "<c1@x>"), "eml")
    assert r.kind == "customer" and row.route == "customer"


def test_polling_the_same_mail_again_changes_nothing(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    mail = _eml(_supplier_email(c, rfqs[0]["supplier_id"]), f"Re: [PP-{rid:05d}]", "<r7@x>")
    _, first = route_incoming(c.session, mail, "eml")
    _, again = route_incoming(c.session, mail, "eml")
    assert first.kind == "supplier" and again is None
    assert c.session.query(InboxEmail).count() == 1


def test_a_person_attaches_an_unattached_mail_or_sends_it_the_customer_way(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    row, r = route_incoming(
        c.session, _eml("random@nowhere.example", f"[PP-{rid:05d}] hello", "<u1@x>"), "eml"
    )
    assert r.kind == "unattached"
    listed = c.get("/mail/unattached").json()
    assert [m["id"] for m in listed] == [row.id] and {c["request_id"] for c in listed[0]["candidates"]} == {
        rid
    }
    target = rfqs[1]
    assert (
        c.post(
            f"/mail/{row.id}/attach", json={"request_id": rid, "supplier_id": target["supplier_id"], "by": ""}
        ).status_code
        == 409
    )
    assert (
        c.post(
            f"/mail/{row.id}/attach", json={"request_id": rid, "supplier_id": 999, "by": "kartel"}
        ).status_code
        == 409
    )
    ok = c.post(
        f"/mail/{row.id}/attach",
        json={"request_id": rid, "supplier_id": target["supplier_id"], "by": "kartel"},
    )
    assert ok.status_code == 200 and ok.json()["route"] == "supplier"
    assert c.get("/mail/unattached").json() == []
    other, _ = route_incoming(c.session, _eml("x@nowhere.example", f"[PP-{rid:05d}] spam", "<u2@x>"), "eml")
    assert c.post(f"/mail/{other.id}/not-supplier", json={"by": "kartel"}).json()["route"] == "customer"


def test_mail_feed_shows_where_a_supplier_mail_went(client):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    route_incoming(
        c.session, _eml(_supplier_email(c, rfqs[0]["supplier_id"]), f"Re: [PP-{rid:05d}]", "<f1@x>"), "eml"
    )
    route_incoming(c.session, _eml("random@nowhere.example", f"[PP-{rid:05d}] ?", "<f2@x>"), "eml")
    feed = {m["subject"]: m for m in c.get("/mail?folder=in").json() if m["direction"] == "in"}
    assert feed[f"Re: [PP-{rid:05d}]"]["status"] == "supplier"
    assert feed[f"[PP-{rid:05d}] ?"]["status"] == "unattached"
    assert len(unattached_mail(c.session)) == 1


def test_eml_files_in_a_folder_are_routed_one_by_one(client, tmp_path):  # noqa: F811
    c = client
    rid, rfqs = _asked(c)
    sup = _supplier_email(c, rfqs[0]["supplier_id"])
    for name, sender, subject, mid in (
        ("a.eml", sup, f"Re: Request for quotation [PP-{rid:05d}]", "<e1@x>"),
        ("b.eml", "buyer@customer.example", "RFQ: 10 pcs", "<e2@x>"),
    ):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = sender, "sales@us.example", subject, mid
        msg["Date"] = format_datetime(datetime(2026, 10, 23, 9, 0, tzinfo=UTC))
        msg.set_content("text")
        (tmp_path / name).write_bytes(msg.as_bytes())
    kinds = [route_incoming(c.session, m, "eml")[1].kind for m in EmlDirReader(tmp_path).fetch_new()]
    assert kinds == ["supplier", "customer"]
