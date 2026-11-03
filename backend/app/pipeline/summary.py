"""The day's summary: one list of what needs a person today. Nothing here is new data. Each section reads
a record some other part of the app already keeps (urgent requests, letters waiting for approval, overdue
deliveries, offers past or near their validity date, suppliers that have not answered a request for
quotation, contracts running out, bank changes waiting for a second person, invoices that differ, supplier
re-checks) and counts it. It sends nothing and changes nothing; each line links to where it is handled.

Thresholds (days of silence, days before an offer or a contract runs out) are set in Settings."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.crm import service as crm
from app.models import (
    Contract,
    Offer,
    PurchaseOrder,
    Rfq,
    Supplier,
    SupplierBankChange,
)
from app.pipeline import delivery, invoices, second, urgency
from app.suppliers import compliance, duplicates

SHOWN = 8  # lines shown per section; the count is always the full one


def _section(key: str, title: str, href: str, rows: list[dict], note: str = "") -> dict:
    return {
        "key": key,
        "title": title,
        "href": href,
        "count": len(rows),
        "items": rows[:SHOWN],
        "more": max(0, len(rows) - SHOWN),
        "note": note,
    }


def _line(text: str, href: str, tone: str = "warn") -> dict:
    return {"text": text, "href": href, "tone": tone}


def _urgent(session: Session, settings: Settings, today: date) -> dict:
    rows = []
    for i in urgency.board(session, settings, today)["items"]:
        tone = "bad" if i["state"] in ("overdue", "today") else "warn"
        when = (
            f"{-i['days_left']} day(s) late"
            if i["state"] == "overdue"
            else "reply today"
            if i["state"] == "today"
            else f"reply by {i['respond_by']}"
            if i["respond_by"]
            else "urgent, no date"
        )
        rows.append(
            _line(
                f"Request #{i['request_id']} {i['subject']}: {when} (step: {i['stage']})",
                f"/requests/{i['request_id']}",
                tone,
            )
        )
    return _section("urgent", "Urgent requests waiting for a quote", "/", rows)


def _approvals(session: Session, settings: Settings) -> dict:
    rows = [
        _line(f"{a['kind']} to {a['counterparty']}: {a['subject']}", "/approvals")
        for a in crm.approvals(session, settings, "pending")
    ]
    return _section("approvals", "Letters waiting for your approval", "/approvals", rows)


def _deliveries(session: Session, today: date) -> dict:
    rows = []
    for o in delivery.overdue_orders(session, today):
        asked = {
            "none": "not asked",
            "waiting": "question waits for approval",
            "sent": f"asked {o['last_asked']}",
        }
        rows.append(
            _line(
                f"PO #{o['order_id']} from {o['supplier']}: {o['overdue_days']} day(s) late, "
                f"{asked[o['question']]}",
                f"/requests/{o['request_id']}",
                "bad",
            )
        )
    return _section("deliveries", "Late deliveries", "/", rows)


def _open_requests(session: Session) -> set[int]:
    ordered = {po.request_id for po in session.scalars(select(PurchaseOrder))}
    return ordered


def _offers(session: Session, settings: Settings, today: date, ordered: set[int]) -> dict:
    rows, limit = [], today + timedelta(days=settings.summary_offer_days)
    names = {s.id: s.name for s in session.scalars(select(Supplier))}
    found = session.scalars(
        select(Offer)
        .where(Offer.valid_until.is_not(None), Offer.valid_until <= limit)
        .order_by(Offer.valid_until)
    )
    for o in found:
        if o.request_id in ordered:
            continue
        left = (o.valid_until - today).days
        what = f"expired {o.valid_until.isoformat()}" if left < 0 else f"expires {o.valid_until.isoformat()}"
        rows.append(
            _line(
                f"Request #{o.request_id}: offer from {names[o.supplier_id]} {what}",
                f"/requests/{o.request_id}",
                "bad" if left < 0 else "warn",
            )
        )
    return _section(
        "offers",
        "Offers past or near their validity date",
        "/",
        rows,
        "Only requests that have no order yet.",
    )


def _silent(session: Session, settings: Settings, today: date, ordered: set[int]) -> dict:
    answered = {(o.request_id, o.supplier_id) for o in session.scalars(select(Offer))}
    names = {s.id: s.name for s in session.scalars(select(Supplier))}
    rows = []
    for r in session.scalars(select(Rfq).where(Rfq.status == "sent").order_by(Rfq.sent_at)):
        if r.request_id in ordered or (r.request_id, r.supplier_id) in answered or r.sent_at is None:
            continue
        days = (today - r.sent_at.date()).days
        if days >= settings.summary_silent_days:
            rows.append(
                _line(
                    f"Request #{r.request_id}: {names[r.supplier_id]} has not answered for {days} day(s)",
                    f"/requests/{r.request_id}",
                )
            )
    return _section(
        "silent",
        "Suppliers that have not answered",
        "/",
        rows,
        f"A request for quotation sent {settings.summary_silent_days} day(s) ago or more, "
        "with no offer entered.",
    )


def _contracts(session: Session, settings: Settings, today: date) -> dict:
    limit = today + timedelta(days=settings.summary_contract_days)
    rows = []
    for c in session.scalars(
        select(Contract)
        .where(Contract.expires_on.is_not(None), Contract.expires_on <= limit)
        .order_by(Contract.expires_on)
    ):
        left = (c.expires_on - today).days
        what = (
            f"ended {c.expires_on.isoformat()}"
            if left < 0
            else f"ends {c.expires_on.isoformat()} (in {left} day(s))"
        )
        rows.append(
            _line(
                f"{c.title}{' / ' + c.counterparty if c.counterparty else ''}: {what}",
                "/legal",
                "bad" if left < 0 else "warn",
            )
        )
    return _section("contracts", "Contracts running out", "/legal", rows)


def _second_person(session: Session) -> dict:
    names = {s.id: s.name for s in session.scalars(select(Supplier))}
    rows = [
        _line(
            f"{names[c.supplier_id]}: new bank account proposed by {c.proposed_by}, needs a different person",
            "/suppliers",
        )
        for c in session.scalars(select(SupplierBankChange).where(SupplierBankChange.status == "pending"))
    ]
    return _section("bank", "Bank details waiting for a second person", "/suppliers", rows)


def _orders_waiting(session: Session) -> dict:
    rows = [
        _line(
            f"Request #{a['request_id']}: order approved by {a['requested_by']} waits for a different person"
            f" ({'; '.join(r['text'] for r in a['risks'])})",
            f"/requests/{a['request_id']}",
            "warn",
        )
        for a in second.listing(session)
    ]
    return _section("orders", "Orders waiting for a second person", "/", rows)


def _invoices(session: Session, settings: Settings) -> dict:
    rows = [
        _line(
            f"PO #{r['order_id']} from {r['supplier']}: invoice {r['number']} differs "
            f"({', '.join(r['kinds'])}), {r['difference_eur']:+.2f} EUR",
            f"/requests/{r['request_id']}",
        )
        for r in invoices.mismatches(session, settings)["rows"]
    ]
    return _section("invoices", "Supplier invoices that differ from the order", "/", rows)


def _rechecks(session: Session, settings: Settings, today: date) -> dict:
    data = compliance.rechecks(session, settings, today)
    rows = []
    for i in data["items"]:
        s = i["screening"]
        if s["attention"]:
            rows.append(_line(f"{i['name']}: last sanctions screening needs attention", "/suppliers", "bad"))
        elif s["status"] == "overdue":
            rows.append(_line(f"{i['name']}: screening overdue by {-s['days_left']} day(s)", "/suppliers"))
    note = (
        f"{data['counts']['never']} supplier(s) never screened, listed under Re-checks on the Suppliers tab."
    )
    return _section("rechecks", "Supplier screenings overdue", "/suppliers", rows, note)


def _duplicates(session: Session) -> dict:
    pairs = [p for p in duplicates.find(session) if p["review"] is None and p["strength"] >= 2]
    rows = [
        _line(
            f"{p['a']['name']} and {p['b']['name']}: {', '.join(r['label'] for r in p['reasons'])}",
            "/suppliers",
        )
        for p in pairs
    ]
    return _section(
        "duplicates",
        "Possible duplicate suppliers to review",
        "/suppliers",
        rows,
        "Strong signals only, not yet reviewed.",
    )


def daily(session: Session, settings: Settings, today: date | None = None) -> dict:
    today = today or date.today()
    ordered = _open_requests(session)
    sections = [
        _urgent(session, settings, today),
        _approvals(session, settings),
        _deliveries(session, today),
        _offers(session, settings, today, ordered),
        _silent(session, settings, today, ordered),
        _contracts(session, settings, today),
        _second_person(session),
        _orders_waiting(session),
        _invoices(session, settings),
        _rechecks(session, settings, today),
        _duplicates(session),
    ]
    return {
        "date": today.isoformat(),
        "total": sum(s["count"] for s in sections),
        "sections": sections,
        "thresholds": {
            "silent_days": settings.summary_silent_days,
            "offer_days": settings.summary_offer_days,
            "contract_days": settings.summary_contract_days,
        },
    }
