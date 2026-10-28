"""Orders past their promised date: the overdue list, and a ready question to the supplier that waits in the
approval queue. Time is moved by editing the promised date: the order itself is made the normal way."""

from datetime import date, timedelta

from app.models import PurchaseOrder
from tests.test_assist import FakeAI, ai  # noqa: F401
from tests.test_delivery import _po, _put
from tests.test_pipeline_e2e import client  # noqa: F401


def _late(c, po, days):
    """Make the order `days` late: its promised date moves into the past, as time would have done."""
    row = c.session.get(PurchaseOrder, po["id"])
    row.promised_date = date.today() - timedelta(days=days)
    c.session.commit()


def test_an_order_on_time_is_not_overdue_and_no_question_is_drafted(client):  # noqa: F811
    c = client
    po = _po(c)
    assert c.get("/orders/overdue").json() == []
    r = c.post(f"/orders/{po['id']}/delay-question")
    assert r.status_code == 409 and "not overdue" in r.json()["detail"]
    _late(c, po, 0)  # promised today is still on time
    assert c.get("/orders/overdue").json() == []


def test_the_overdue_list_is_sorted_with_the_most_late_first(client):  # noqa: F811
    c = client
    a, b = _po(c), _po(c)
    _late(c, a, 3)
    _late(c, b, 9)
    rows = c.get("/orders/overdue").json()
    assert [r["order_id"] for r in rows] == [b["id"], a["id"]]
    top = rows[0]
    assert top["overdue_days"] == 9 and top["supplier"] and top["question"] == "none"
    assert top["promised_date"] == (date.today() - timedelta(days=9)).isoformat()
    assert top["status"] == "ordered" and top["request_id"] == b["request_id"]


def test_a_delivered_or_cancelled_order_drops_off_the_list(client):  # noqa: F811
    c = client
    a, b = _po(c), _po(c)
    _late(c, a, 5)
    _late(c, b, 5)
    assert len(c.get("/orders/overdue").json()) == 2
    _put(c, a, status="delivered", reason="arrived")
    _put(c, b, status="cancelled", reason="customer withdrew")
    assert c.get("/orders/overdue").json() == []
    assert c.post(f"/orders/{a['id']}/delay-question").status_code == 409


def test_the_question_is_a_letter_that_waits_for_approval_and_is_not_repeated(client):  # noqa: F811
    c = client
    po = _po(c)
    _late(c, po, 4)
    promised = (date.today() - timedelta(days=4)).isoformat()
    letter = c.post(f"/orders/{po['id']}/delay-question").json()
    assert letter["kind"] == "delay" and letter["status"] == "draft" and letter["order_id"] == po["id"]
    assert letter["supplier"] and f"{po['id']}" in letter["reason"] and "4 day(s) late" in letter["reason"]
    assert promised in letter["body"] and ("kasni" in letter["body"] or "delay" in letter["body"])
    assert letter["language"] in ("sr", "en")
    assert letter["drafted_by"] == "template" and "[" in letter["subject"]
    queue = [x for x in c.get("/approvals").json() if x["kind"] == "delay"]
    assert len(queue) == 1 and queue[0]["status"] == "draft"
    row = c.get("/orders/overdue").json()[0]
    assert row["question"] == "waiting" and row["question_letter_id"] == letter["id"]
    assert c.post(f"/orders/{po['id']}/delay-question").status_code == 409  # one waiting draft

    before = len(c.outbox)
    sent = c.post(f"/letters/{letter['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    assert sent.status_code == 200 and len(c.outbox) == before + 1
    row = c.get("/orders/overdue").json()[0]
    assert row["question"] == "sent" and row["last_asked"] == date.today().isoformat()
    again = c.post(f"/orders/{po['id']}/delay-question")
    assert again.status_code == 409 and "wait 3 days" in again.json()["detail"]  # asked just now


def test_a_rejected_question_does_not_block_a_new_one(client):  # noqa: F811
    c = client
    po = _po(c)
    _late(c, po, 2)
    letter = c.post(f"/orders/{po['id']}/delay-question").json()
    c.post(f"/letters/{letter['id']}/decision", json={"approve": False, "decided_by": "kartel"})
    assert c.get("/orders/overdue").json()[0]["question"] == "none"
    assert c.post(f"/orders/{po['id']}/delay-question").status_code == 200


def test_one_click_prepares_a_question_for_every_overdue_order_and_sends_nothing(client):  # noqa: F811
    c = client
    a, b, fine = _po(c), _po(c), _po(c)
    _late(c, a, 6)
    _late(c, b, 1)
    before = len(c.outbox)
    done = c.post("/orders/overdue/questions").json()
    assert sorted(x["order_id"] for x in done["letters"]) == sorted([a["id"], b["id"]])
    assert all(x["status"] == "draft" for x in done["letters"]) and done["skipped"] == []
    assert len(c.outbox) == before  # nothing left the system
    assert fine["id"] not in [x["order_id"] for x in done["letters"]]
    second = c.post("/orders/overdue/questions").json()
    assert second["letters"] == [] and len(second["skipped"]) == 2
    assert all("already waiting" in s["reason"] for s in second["skipped"])


def test_an_ai_draft_is_used_only_if_it_names_the_promised_date(ai):  # noqa: F811
    c, fake = ai
    po = _po(c)
    _late(c, po, 5)
    promised = (date.today() - timedelta(days=5)).isoformat()
    fake.answers["delay_question_draft"] = lambda v: {
        "confidence": 0.9,
        "subject": f"Late delivery [{v['ref']}]",
        "body": f"Dear {v['supplier_name']}, order {v['ref']} was promised for {v['promised_date']}:\n"
        f"{v['items']}\nPlease give the reason and a new date. PowerProcurement",
    }
    good = c.post(f"/orders/{po['id']}/delay-question").json()
    assert good["drafted_by"] == "AI · fake-model" and promised in good["body"]
    assert fake.calls[-1][1]["promised_date"] == promised
    c.post(f"/letters/{good['id']}/decision", json={"approve": False, "decided_by": "kartel"})
    fake.answers["delay_question_draft"] = lambda v: {
        "confidence": 0.9,
        "subject": f"Late [{v['ref']}]",
        "body": f"Dear {v['supplier_name']}, order {v['ref']} is late:\n{v['items']}\nPlease reply soon.",
    }
    weak = c.post(f"/orders/{po['id']}/delay-question").json()
    assert weak["drafted_by"] == "template · AI draft rejected" and promised in weak["body"]
