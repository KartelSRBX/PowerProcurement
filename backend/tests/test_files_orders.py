"""Supplier answers as files (PDF, Excel, CSV, text) and the two order letters (confirmation to the customer,
delivery question to the supplier)."""

import base64
import io

import pytest
from openpyxl import Workbook

from app.assist import files
from app.pipeline.service import PipelineError
from tests.test_assist import FakeAI, ai, quote_sent, rfq_body, sent_flow  # noqa: F401
from tests.test_pipeline_e2e import client  # noqa: F401


def make_pdf(text: str | None) -> bytes:
    """A one-page PDF; text=None gives a page with no text layer, like a scan."""
    stream = b"" if text is None else f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


def make_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Offer"
    ws.append(["Item", "Unit price", "Currency", "Lead time"])
    ws.append(["STM32F407VGT6", 12.5, "EUR", "10 days"])
    ws.append([None, None, None, None])
    ws.append(["100nF 0603", 0.02, "EUR", "4 days"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---- the reader ---------------------------------------------------------------------------------------


def test_pdf_text_is_read():
    text = files.extract_text("offer.pdf", make_pdf("Unit price 12.50 EUR, lead time 10 days"))
    assert text.startswith("[File: offer.pdf]") and "Unit price 12.50 EUR" in text


def test_pdf_without_text_layer_is_refused_with_a_way_out():
    with pytest.raises(PipelineError, match="no text layer"):
        files.extract_text("scan.pdf", make_pdf(None))
    with pytest.raises(PipelineError, match="could not be read"):
        files.extract_text("broken.pdf", b"%PDF-1.4 this is not a pdf")


def test_excel_rows_are_read_and_empty_rows_skipped():
    text = files.extract_text("offer.xlsx", make_xlsx())
    assert "Sheet: Offer" in text
    assert "STM32F407VGT6 | 12.5 | EUR | 10 days" in text and "100nF 0603 | 0.02 | EUR | 4 days" in text
    assert "\n\n" not in text.split("Sheet: Offer\n", 1)[1]
    with pytest.raises(PipelineError, match="could not be opened"):
        files.extract_text("bad.xlsx", b"not a zip")


def test_csv_and_text_in_common_encodings():
    csv_text = files.extract_text("p.csv", b"Item;Price\nSTM32;12,5\n")
    assert "Item | Price" in csv_text and "STM32 | 12,5" in csv_text
    cp1250 = files.extract_text("pismo.txt", "Cena 12 EUR, rok isporuke 10 dana, šifra č".encode("cp1250"))
    assert "šifra č" in cp1250


def test_unsupported_empty_and_oversized_files_are_refused():
    for name, data, why in [
        ("a.xls", b"x", "old .xls"),
        ("a.exe", b"x", "not read"),
        ("a.pdf", b"", "empty"),
        ("a.txt", b"x" * (files.MAX_BYTES + 1), "larger than"),
    ]:
        with pytest.raises(PipelineError, match=why):
            files.extract_text(name, data)
    long = files.extract_text("a.txt", ("word " * 10000).encode())
    assert len(long) < 20000 and "text cut" in long


# ---- through the API -----------------------------------------------------------------------------------


def upload(c, rid, sid, name, data, by="kartel"):
    return c.post(
        f"/requests/{rid}/replies/file",
        json={
            "supplier_id": sid,
            "filename": name,
            "content_base64": base64.b64encode(data).decode(),
            "entered_by": by,
        },
    )


def test_uploaded_excel_is_read_like_a_pasted_answer(ai):  # noqa: F811
    c, fake = ai
    rid, sids = sent_flow(c, fake)
    fake.answers["supplier_reply"] = {
        "confidence": 0.9,
        "is_offer": True,
        "lines": [
            {"item": 1, "unit_price": 12.5, "currency": "EUR", "lead_time_days": 10},
            {"item": 2, "unit_price": 0.02, "currency": "EUR", "lead_time_days": 4},
        ],
    }
    r = upload(c, rid, sids[0], "offer.xlsx", make_xlsx()).json()
    assert r["text"].startswith("[File: offer.xlsx]") and "STM32F407VGT6 | 12.5" in r["text"]
    assert r["proposal"]["total_price"] == 6290.0 and r["read_by"] == "fake-model"
    sent_text = fake.calls[-1][1]["text"]
    assert "STM32F407VGT6 | 12.5 | EUR" in sent_text  # the model is shown what is in the file
    assert c.get(f"/requests/{rid}/offers").json() == []  # still only a proposal


def test_upload_problems_are_plain_409s(ai):  # noqa: F811
    c, fake = ai
    rid, sids = sent_flow(c, fake)
    assert upload(c, rid, sids[0], "scan.pdf", make_pdf(None)).status_code == 409
    assert upload(c, rid, sids[0], "x.docx", b"zip").status_code == 409
    bad = c.post(
        f"/requests/{rid}/replies/file",
        json={"supplier_id": sids[0], "filename": "a.txt", "content_base64": "%%%", "entered_by": "kartel"},
    )
    assert bad.status_code == 409 and "decoded" in bad.json()["detail"]
    assert upload(c, rid, sids[0], "a.txt", b"price 5", by=" ").status_code == 409
    assert c.get(f"/requests/{rid}/replies").json() == []


def test_upload_without_ai_still_hands_the_text_to_the_person(client):  # noqa: F811
    c = client
    rid = _sent(c)
    sid = c.get(f"/requests/{rid}/shortlist").json()[0]["supplier_id"]
    r = upload(c, rid, sid, "offer.pdf", make_pdf("we offer 5000 EUR")).json()
    assert r["read_by"] == "manual" and "we offer 5000 EUR" in r["text"]
    assert r["proposal"]["total_price"] is None


def _sent(c):
    from tests.test_pipeline_e2e import new_request

    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    for d in c.post(f"/requests/{rid}/rfqs/draft").json():
        c.post(f"/rfqs/{d['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    return rid


# ---- order confirmation and delivery question --------------------------------------------------------------


def with_order(c, fake):
    fake.answers["quote_draft"] = RuntimeError("skip")
    rid, q = quote_sent(c, fake)
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    po = c.post(f"/requests/{rid}/orders", json={"approved_by": "kartel"}).json()
    return rid, q, po


def test_order_confirmation_carries_the_exact_price_and_waits_for_approval(ai):  # noqa: F811
    c, fake = ai
    rid, q, po = with_order(c, fake)
    price_text = f"{q['price']:,.2f} EUR"
    lead = c.get(f"/requests/{rid}/offers").json()[0]["lead_time_days"]
    fake.answers["order_confirmation_draft"] = lambda v: {
        "confidence": 0.9,
        "subject": f"Order confirmation [{v['ref']}]",
        "body": f"Dear customer, thank you. Order {v['ref']}:\n{v['items']}\nTotal {v['price_text']}, "
        f"delivery {v['lead_days']} days. We will tell you if anything changes. PowerProcurement",
    }
    letter = c.post(f"/orders/{po['id']}/customer-confirmation").json()
    assert letter["kind"] == "confirmation" and letter["status"] == "draft" and letter["order_id"] == po["id"]
    assert letter["drafted_by"] == "AI · fake-model" and price_text in letter["body"]
    assert f"{lead} days" in letter["body"] and letter["to_email"] == "buyer@customer.example"
    assert c.post(f"/orders/{po['id']}/customer-confirmation").status_code == 409  # one per order
    before = len(c.outbox)
    assert any(x["kind"] == "confirmation" for x in c.get("/approvals").json())
    done = c.post(f"/letters/{letter['id']}/decision", json={"approve": True, "decided_by": "kartel"}).json()
    assert done["status"] == "sent" and len(c.outbox) == before + 1
    assert c.outbox[-1]["to"] == "buyer@customer.example"
    assert c.post(f"/orders/{po['id']}/customer-confirmation").status_code == 409  # sent counts too


def test_order_confirmation_rejects_a_draft_that_changes_the_price(ai):  # noqa: F811
    c, fake = ai
    rid, q, po = with_order(c, fake)
    fake.answers["order_confirmation_draft"] = lambda v: {
        "confidence": 0.9,
        "subject": f"Order confirmation [{v['ref']}]",
        "body": f"Dear customer, order {v['ref']} confirmed for 1.00 EUR in total. {v['items']} Thank you.",
    }
    letter = c.post(f"/orders/{po['id']}/customer-confirmation").json()
    assert letter["drafted_by"] == "template · AI draft rejected"
    assert f"{q['price']:,.2f} EUR" in letter["body"]


def test_delivery_question_goes_to_the_supplier_and_can_be_repeated_after_sending(ai):  # noqa: F811
    c, fake = ai
    rid, q, po = with_order(c, fake)
    fake.answers["delivery_question_draft"] = lambda v: {
        "confidence": 0.9,
        "subject": f"Delivery [{v['ref']}]",
        "body": f"Dear {v['supplier_name']}, about order {v['ref']}:\n{v['items']}\nPlease confirm dispatch "
        "date, carrier, tracking number and documents. Thank you, PowerProcurement",
    }
    letter = c.post(f"/orders/{po['id']}/delivery-question").json()
    assert letter["kind"] == "delivery" and letter["supplier"] and letter["drafted_by"] == "AI · fake-model"
    assert c.post(f"/orders/{po['id']}/delivery-question").status_code == 409  # one waiting draft
    before = len(c.outbox)
    c.post(f"/letters/{letter['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    assert len(c.outbox) == before + 1 and "sales@" in c.outbox[-1]["to"]
    again = c.post(f"/orders/{po['id']}/delivery-question")
    assert again.status_code == 200  # asking again later is fine
    assert any(m["kind"] == "delivery" for m in c.get("/mail?folder=out").json())


def test_order_letters_use_templates_without_ai(client):  # noqa: F811
    c = client
    from tests.test_pipeline_e2e import new_request, run_to_offers

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
    a = c.post(f"/orders/{po['id']}/customer-confirmation").json()
    b = c.post(f"/orders/{po['id']}/delivery-question").json()
    assert a["drafted_by"] == "template" and "[PP-" in a["subject"] and "STM32F407VGT6" in a["body"]
    assert b["drafted_by"] == "template"
    assert "tracking" in b["body"].lower() or "praćenje" in b["body"]
    assert c.post("/orders/9999/customer-confirmation").status_code == 404
