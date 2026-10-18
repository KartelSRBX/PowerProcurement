"""The AI-assisted steps with a fake model: what the model may do, what code still checks, and that every
step still works when AI is off or fails."""

import pytest
from sqlalchemy import select

from app.ai.base import AIResult
from app.ai.tasks import set_adapter_factory
from app.config import get_settings
from app.main import app
from app.models import AuditLog, Letter
from tests.test_pipeline_e2e import SETTINGS, client, new_request, run_to_offers  # noqa: F401

SERBIAN_OK = "Poštovani, molimo vas za ponudu. Hvala. " * 3


class FakeAI:
    def __init__(self):
        self.answers: dict = {}
        self.calls: list[tuple[str, dict]] = []

    def extract(self, prompt, variables, schema):
        self.calls.append((prompt.id, variables))
        answer = self.answers[prompt.id]
        answer = answer(variables) if callable(answer) else answer
        if isinstance(answer, Exception):
            raise answer
        return AIResult(
            parsed=schema.model_validate(answer),
            model="fake-model",
            prompt_id=prompt.id,
            prompt_version=prompt.version,
        )

    def called(self, prompt_id: str) -> int:
        return sum(1 for p, _ in self.calls if p == prompt_id)


@pytest.fixture
def ai(client):  # noqa: F811
    fake = FakeAI()
    cfg = SETTINGS.model_copy(update={"ai_provider": "anthropic", "anthropic_api_key": "test-key"})
    app.dependency_overrides[get_settings] = lambda: cfg
    set_adapter_factory(lambda s: fake)
    yield client, fake
    set_adapter_factory(None)


def supplier_ids(c):
    return {s["name"]: s["id"] for s in c.get("/suppliers").json()}


def rfq_body(variables, ok=True):
    lines = variables["items"].splitlines()
    items = "\n".join(f"- {ln.split('. ', 1)[1]}" for ln in lines) if ok else "- something else"
    ref = variables["ref"]
    return {
        "subject": f"Request for quotation [{ref}]",
        "body": f"Dear {variables['supplier_name']},\n\nplease quote:\n{items}\n\nThank you,",
        "confidence": 0.95,
    }


# ---- AI off: everything keeps working -------------------------------------------------------------


def test_ai_off_uses_templates_and_hand_entry_still_works(client):  # noqa: F811
    c = client
    rid = new_request(c)
    disc = c.post(f"/requests/{rid}/discover").json()
    assert disc["ai"] == {"used": False, "suggested": 0, "note": None}
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    assert drafts and all(d["drafted_by"] == "template" for d in drafts)
    for d in drafts:
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    sid = drafts[0]["supplier_id"]
    # hand entry: the reply screen works without a model, the person types the numbers
    r = c.post(
        f"/requests/{rid}/replies",
        json={"supplier_id": sid, "text": "we offer 5000 EUR", "entered_by": "kartel"},
    ).json()
    assert r["read_by"] == "manual" and r["ai"]["used"] is False and r["proposal"]["total_price"] is None
    offer = c.post(
        f"/replies/{r['id']}/confirm",
        json={"confirmed_by": "kartel", "total_price": 5000, "currency": "EUR", "lead_time_days": 7},
    ).json()
    assert offer["source"] == "manual"
    for url, body in [
        (f"/requests/{rid}/score/explain", {}),
        ("/analytics/narrative", {"topic": "messages"}),
        ("/mail/parse-all", {}),
    ]:
        resp = c.post(url, json=body)
        assert resp.status_code == 409 and "AI is off" in resp.json()["detail"]


# ---- step 3: supplier pool ------------------------------------------------------------------------


def test_pool_suggestions_are_unticked_and_pass_the_same_filters(ai):
    c, fake = ai
    rid = new_request(c)
    names = supplier_ids(c)
    c.post(f"/requests/{rid}/discover")  # baseline with the fake not yet scripted would fail: script first
    base = {s["supplier_id"] for s in c.get(f"/requests/{rid}/shortlist").json()}
    extra = next(
        s["id"]
        for s in c.get("/suppliers").json()
        if "electronics" in s["categories"] and not s["sanctioned"] and s["id"] not in base
    )
    fake.answers["supplier_pool"] = {
        "confidence": 0.9,
        "suggestions": [
            {"supplier_id": extra, "items": [1, 2, 9], "reason": "distributes the STM32 brand"},
            {
                "supplier_id": names["Vostok Parts Trading"],
                "items": [1],
                "reason": "sanctioned: must be refused",
            },
            {"supplier_id": 99999, "items": [1], "reason": "does not exist"},
        ],
        "explanations": [{"supplier_id": sorted(base)[0], "reason": "covers both items and has many deals"}],
    }
    out = c.post(f"/requests/{rid}/discover").json()
    assert out["ai"] == {"used": True, "suggested": 1, "note": None}
    rows = {s["supplier_id"]: s for s in c.get(f"/requests/{rid}/shortlist").json()}
    assert rows[extra]["selected"] is False and rows[extra]["reason"].startswith("AI suggestion: ")
    assert rows[extra]["covered_items"] == 2
    assert names["Vostok Parts Trading"] not in rows and 99999 not in rows
    assert "AI: covers both items" in rows[sorted(base)[0]]["reason"]
    # unticked means it is not asked until a person ticks it
    ids = {d["supplier_id"] for d in c.post(f"/requests/{rid}/rfqs/draft").json()}
    assert extra not in ids


def test_pool_low_confidence_and_failure_change_nothing(ai):
    c, fake = ai
    rid = new_request(c)
    fake.answers["supplier_pool"] = {
        "confidence": 0.3,
        "suggestions": [{"supplier_id": 1, "items": [1], "reason": "x"}],
        "explanations": [],
    }
    out = c.post(f"/requests/{rid}/discover").json()
    assert out["ai"]["used"] is False and "not sure enough" in out["ai"]["note"]
    fake.answers["supplier_pool"] = RuntimeError("network down")
    out = c.post(f"/requests/{rid}/discover").json()
    assert out["ai"]["used"] is False and "failed" in out["ai"]["note"]
    assert out["shortlist"] >= 2
    failures = c.app.state if False else None  # noqa: F841
    assert any(a.action == "ai.failed" for a in c.session.scalars(select(AuditLog)))


# ---- step 4: letters ------------------------------------------------------------------------------


def test_rfq_drafts_use_the_model_only_when_every_item_is_there(ai):
    c, fake = ai
    rid = new_request(c)
    fake.answers["supplier_pool"] = {"confidence": 0.9}
    c.post(f"/requests/{rid}/discover")
    fake.answers["rfq_draft"] = lambda v: rfq_body(v)
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    assert drafts and all(d["drafted_by"] == "AI · fake-model" for d in drafts)
    assert all(f"[PP-{rid:05d}]" in d["subject"] for d in drafts)
    assert all("STM32F407VGT6" in d["body"] and "2000" in d["body"] for d in drafts)
    # a draft that drops the items is refused and the template is used
    rid2 = new_request(c)
    c.post(f"/requests/{rid2}/discover")
    fake.answers["rfq_draft"] = lambda v: rfq_body(v, ok=False)
    drafts = c.post(f"/requests/{rid2}/rfqs/draft").json()
    assert all(d["drafted_by"] == "template · AI draft rejected" for d in drafts)
    assert all("STM32F407VGT6" in d["body"] for d in drafts)


def test_quote_draft_must_carry_the_exact_price(ai):
    c, fake = ai
    rid = new_request(c)
    fake.answers["supplier_pool"] = {"confidence": 0.9}
    fake.answers["rfq_draft"] = lambda v: rfq_body(v)
    run_to_offers(c, rid)
    ranked = c.post(f"/requests/{rid}/score").json()
    best = next(r for r in ranked if not r["excluded"])

    def quote(v, price_ok):
        shown = v["price_text"] if price_ok else "1.00 EUR"
        return {
            "subject": f"Quotation [{v['ref']}]",
            "body": f"Dear customer,\n\nSTM32F407VGT6 microcontroller, 100nF 0603 capacitors.\nTotal {shown},"
            f" lead time {v['lead_days']} days. Valid 14 days.\n\nPowerProcurement",
            "confidence": 0.9,
        }

    fake.answers["quote_draft"] = lambda v: quote(v, price_ok=False)
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    assert q["drafted_by"] == "template · AI draft rejected" and "Total price" in q["body"]
    fake.answers["quote_draft"] = lambda v: quote(v, price_ok=True)
    q2 = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    assert q2["drafted_by"] == "AI · fake-model" and f"{q2['price']:,.2f} EUR" in q2["body"]


# ---- step 5: replies ------------------------------------------------------------------------------


def sent_flow(c, fake):
    fake.answers["supplier_pool"] = {"confidence": 0.9}
    fake.answers["rfq_draft"] = lambda v: rfq_body(v)
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    for d in c.post(f"/requests/{rid}/rfqs/draft").json():
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    return rid, [s["supplier_id"] for s in c.get(f"/requests/{rid}/shortlist").json() if s["selected"]]


def test_reply_total_is_added_up_by_code_and_needs_confirmation(ai):
    c, fake = ai
    rid, sids = sent_flow(c, fake)
    fake.answers["supplier_reply"] = {
        "confidence": 0.9,
        "is_offer": True,
        "lines": [
            {"item": 1, "unit_price": 12.5, "currency": "EUR", "lead_time_days": 10, "moq": 100},
            {"item": 2, "unit_price": 0.02, "currency": "EUR", "lead_time_days": 4},
        ],
        "payment_terms": "30 days",
        "missing": ["warranty"],
        "problems": [],
        "notes": "",
    }
    r = c.post(
        f"/requests/{rid}/replies",
        json={"supplier_id": sids[0], "text": "see prices", "entered_by": "kartel"},
    ).json()
    p = r["proposal"]
    assert r["ai"]["used"] and r["read_by"] == "fake-model"
    assert p["total_price"] == 500 * 12.5 + 2000 * 0.02 and p["currency"] == "EUR"
    assert p["lead_time_days"] == 10 and p["covers_all_items"] is True and p["moq_ok"] is True
    assert r["missing"] == ["warranty"]
    assert c.get(f"/requests/{rid}/offers").json() == []  # nothing counts until a person confirms
    offer = c.post(
        f"/replies/{r['id']}/confirm",
        json={"confirmed_by": "kartel", **{k: p[k] for k in ("total_price", "currency", "lead_time_days")}},
    ).json()
    assert offer["source"] == "ai-reviewed" and offer["total_price"] == 6290.0
    assert (
        c.post(
            f"/replies/{r['id']}/confirm",
            json={"confirmed_by": "kartel", "total_price": 1, "currency": "EUR", "lead_time_days": 1},
        ).status_code
        == 409
    )
    # an answer that only covers one item and a MOQ above the quantity is flagged for the person
    fake.answers["supplier_reply"] = {
        "confidence": 0.9,
        "is_offer": True,
        "lines": [{"item": 1, "unit_price": 10, "currency": "EUR", "moq": 1000}],
    }
    r2 = c.post(
        f"/requests/{rid}/replies", json={"supplier_id": sids[1], "text": "partial", "entered_by": "kartel"}
    ).json()
    assert r2["proposal"]["covers_all_items"] is False and r2["proposal"]["moq_ok"] is False
    assert any("no price" in w for w in r2["warnings"]) and any("minimum order" in w for w in r2["warnings"])


def test_reply_mixed_currency_is_left_to_the_person(ai):
    c, fake = ai
    rid, sids = sent_flow(c, fake)
    fake.answers["supplier_reply"] = {
        "confidence": 0.9,
        "is_offer": True,
        "lines": [
            {"item": 1, "unit_price": 12, "currency": "EUR"},
            {"item": 2, "unit_price": 3, "currency": "RSD"},
        ],
    }
    r = c.post(
        f"/requests/{rid}/replies", json={"supplier_id": sids[0], "text": "mixed", "entered_by": "kartel"}
    ).json()
    assert r["proposal"]["total_price"] is None and any("different currencies" in w for w in r["warnings"])
    assert "price" in r["missing"]


def test_reply_requires_a_sent_letter_and_a_name(ai):
    c, fake = ai
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    sid = c.get(f"/requests/{rid}/shortlist").json()[0]["supplier_id"]
    body = {"supplier_id": sid, "text": "price list attached", "entered_by": "kartel"}
    assert c.post(f"/requests/{rid}/replies", json=body).status_code == 409  # nothing sent yet
    assert c.post(f"/requests/{rid}/replies", json=body | {"entered_by": " "}).status_code == 409


def test_score_explanation_only_for_real_offers(ai):
    c, fake = ai
    rid, _ = sent_flow(c, fake)
    c.post(f"/requests/{rid}/offers/simulate")
    ranked = c.post(f"/requests/{rid}/score").json()
    top = ranked[0]["offer_id"]
    fake.answers["score_explain"] = {
        "confidence": 0.9,
        "summary": "Dunav looks strongest on price and lead time.",
        "suppliers": [{"offer_id": top, "text": "Best price."}, {"offer_id": 424242, "text": "ghost"}],
    }
    out = c.post(f"/requests/{rid}/score/explain", json={}).json()
    assert out["summary"].startswith("Dunav") and out["suppliers"] == {str(top): "Best price."}
    assert out["ranked"][0]["offer_id"] == top
    sent_vars = fake.calls[-1][1]["ranked"]
    assert '"total"' in sent_vars and "landed_cost_eur" in sent_vars  # the model is shown code's numbers


# ---- step 6: follow-ups ---------------------------------------------------------------------------


def test_followups_for_silence_and_for_gaps_go_through_approval(ai):
    c, fake = ai
    rid, sids = sent_flow(c, fake)
    assert c.get(f"/requests/{rid}/followups").json() == []  # just sent: nobody is late yet
    cands = c.get(f"/requests/{rid}/followups?silent_days=0").json()
    assert {x["supplier_id"] for x in cands} == set(sids) and all(x["kind"] == "unanswered" for x in cands)
    # one supplier answers with a gap
    fake.answers["supplier_reply"] = {
        "confidence": 0.9,
        "is_offer": True,
        "lines": [
            {"item": 1, "unit_price": 10, "currency": "EUR"},
            {"item": 2, "unit_price": 1, "currency": "EUR"},
        ],
        "missing": ["lead time", "validity"],
    }
    c.post(
        f"/requests/{rid}/replies", json={"supplier_id": sids[0], "text": "prices", "entered_by": "kartel"}
    )
    kinds = {x["supplier_id"]: x for x in c.get(f"/requests/{rid}/followups?silent_days=0").json()}
    assert kinds[sids[0]]["kind"] == "incomplete" and kinds[sids[0]]["needs"] == ["lead time", "validity"]
    fake.answers["followup_draft"] = lambda v: {
        "subject": f"Follow-up [{v['ref']}]",
        "body": f"Dear {v['supplier_name']}, could you please confirm: {v['needs']}. Thank you,",
        "confidence": 0.9,
    }
    letters = c.post(f"/requests/{rid}/followups", json={"silent_days": 0}).json()
    assert len(letters) == len(sids) and all(
        x["status"] == "draft" and x["kind"] == "followup" for x in letters
    )
    mine = next(x for x in letters if x["supplier_id"] == sids[0])
    assert "lead time; validity" in mine["body"] and mine["drafted_by"] == "AI · fake-model"
    assert c.post(f"/requests/{rid}/followups", json={"silent_days": 0}).json() == []  # no duplicates
    # they wait in the approval queue and send only on a named approval
    queue = c.get("/approvals").json()
    assert {x["kind"] for x in queue if x["request_id"] == rid} >= {"followup"}
    before = len(c.outbox)
    assert (
        c.post(f"/letters/{mine['id']}/decision", json={"approve": True, "decided_by": " "}).status_code
        == 409
    )
    assert len(c.outbox) == before
    done = c.post(f"/letters/{mine['id']}/decision", json={"approve": True, "decided_by": "kartel"}).json()
    assert done["status"] == "sent" and len(c.outbox) == before + 1
    assert any(m["kind"] == "followup" for m in c.get("/mail?folder=out").json())
    # asked once already: not asked again until they write back
    assert sids[0] not in {x["supplier_id"] for x in c.get(f"/requests/{rid}/followups?silent_days=0").json()}


def test_followup_without_ai_uses_the_template(client):  # noqa: F811
    c = client
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    for d in c.post(f"/requests/{rid}/rfqs/draft").json():
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    letters = c.post(f"/requests/{rid}/followups", json={"silent_days": 0}).json()
    assert letters and all(x["drafted_by"] == "template" and "[PP-" in x["subject"] for x in letters)
    assert all(x["reason"].startswith("no answer yet") for x in letters)
    assert c.session.scalars(select(Letter)).first() is not None


# ---- step 7: customer side and invoice ------------------------------------------------------------


def quote_sent(c, fake):
    rid, _ = sent_flow(c, fake)
    c.post(f"/requests/{rid}/offers/simulate")
    best = next(r for r in c.post(f"/requests/{rid}/score").json() if not r["excluded"])
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    return rid, q


def test_customer_reply_is_read_into_a_proposal_and_reminder_is_a_draft(ai):
    c, fake = ai
    fake.answers["quote_draft"] = RuntimeError("skip")
    rid, q = quote_sent(c, fake)
    fake.answers["customer_answer"] = {
        "confidence": 0.9,
        "kind": "counter",
        "price": 6000,
        "currency": "EUR",
        "reason": "budget is tight",
    }
    out = c.post(f"/quotes/{q['id']}/customer-reply/read", json={"text": "Can you do 6000 EUR?"}).json()
    assert out["kind"] == "counter" and out["price"] == 6000 and out["currency"] == "EUR"
    assert c.get(f"/requests/{rid}/outcomes").json() == []  # reading is not recording
    fake.answers["customer_answer"] = {"confidence": 0.9, "kind": "accepted", "price": 5000}
    out = c.post(f"/quotes/{q['id']}/customer-reply/read", json={"text": "Agreed."}).json()
    assert out["kind"] == "accepted" and out["price"] is None  # a price is kept only for a counter
    fake.answers["reminder_draft"] = lambda v: {
        "subject": f"Reminder [{v['ref']}]",
        "body": f"Dear customer, a quick reminder about our quotation {v['price_text']}. PowerProcurement",
        "confidence": 0.9,
    }
    letter = c.post(f"/quotes/{q['id']}/reminder").json()
    assert (
        letter["kind"] == "reminder"
        and letter["status"] == "draft"
        and letter["drafted_by"] == "AI · fake-model"
    )
    assert c.post(f"/quotes/{q['id']}/reminder").status_code == 409  # one waiting draft at a time
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    assert c.post(f"/quotes/{q['id']}/reminder").status_code == 409  # they answered


def test_invoice_request_is_drafted_edited_and_then_sent(ai):
    c, fake = ai
    fake.answers["quote_draft"] = RuntimeError("skip")
    rid, q = quote_sent(c, fake)
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).json()
    ref = f"PP-{rid:05d}"
    fake.answers["invoice_draft"] = lambda v: {
        "subject": f"Invoice request [{ref}]",
        "body": f"Dear {v['supplier_name']}, please send the pro-forma invoice for order {ref}: "
        f"{v['items']} Total {v['total_text']}. Thank you, PowerProcurement",
        "confidence": 0.9,
    }
    draft = c.get(f"/orders/{po['id']}/invoice-draft").json()
    assert draft["drafted_by"] == "AI · fake-model" and ref in draft["body"] and "RSD" in draft["body"]
    before = len(c.outbox)
    sent = c.post(
        f"/orders/{po['id']}/invoice-request",
        json={"approved_by": "kartel", "subject": "Edited subject", "body": draft["body"] + " (edited)"},
    )
    assert (
        sent.status_code == 200
        and c.outbox[-1]["subject"] == "Edited subject"
        and len(c.outbox) == before + 1
    )
    assert c.post(f"/orders/{po['id']}/invoice-request", json={"approved_by": "kartel"}).status_code == 409


def test_invoice_request_without_text_still_works(client):  # noqa: F811
    c = client
    rid = new_request(c)
    run_to_offers(c, rid)
    best = next(r for r in c.post(f"/requests/{rid}/score").json() if not r["excluded"])
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).json()
    assert c.get(f"/orders/{po['id']}/invoice-draft").json()["drafted_by"] == "template"
    assert c.post(f"/orders/{po['id']}/invoice-request", json={"approved_by": "kartel"}).status_code == 200


# ---- step 1: the inbox and the analytics in words -------------------------------------------------


def test_parse_all_reads_every_stored_email_once(ai):
    c, fake = ai
    assert c.post("/mail/demo-load").json()["added"] == 16
    fake.answers["intake"] = lambda v: {
        "confidence": 0.9,
        "is_request": "quote" in v["subject"].lower() or "ponuda" in v["subject"].lower(),
        "language": "en",
        "category": "electronics",
        "items": [{"description": "part", "quantity": 1}] if "quote" in v["subject"].lower() else [],
    }
    out = c.post("/mail/parse-all", json={"limit": 50}).json()
    assert out["failed"] == 0 and out["left"] == 0
    assert out["parsed"] + out["needs_review"] + out["not_request"] == 16
    assert c.post("/mail/parse-all", json={"limit": 50}).json()["parsed"] == 0  # nothing left to read
    assert fake.called("intake") == 16
    c.post("/mail/demo-load")
    fake.answers["intake"] = RuntimeError("down")
    assert c.post("/mail/parse-all", json={}).json()["failed"] == 0  # all were already read


def test_narrative_describes_the_numbers_it_was_given(ai):
    c, fake = ai
    fake.answers["narrative"] = {
        "confidence": 0.9,
        "headline": "Few emails so far.",
        "points": ["0 requests were created."],
    }
    out = c.post("/analytics/narrative", json={"topic": "messages", "days": 14}).json()
    assert out["headline"] == "Few emails so far." and out["model"] == "fake-model"
    assert '"funnel"' in fake.calls[-1][1]["data"] or "funnel" in fake.calls[-1][1]["data"].lower()
    assert c.post("/analytics/narrative", json={"topic": "pricing"}).status_code == 200
    assert c.post("/analytics/narrative", json={"topic": "nonsense"}).status_code == 409
