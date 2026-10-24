"""Step 5, AI part: read a supplier's answer (pasted text) into offer fields. The model only extracts what
is written; code adds up the prices, and a person reviews and confirms before an offer exists. Without
AI the same screen works by hand."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tasks import ai_enabled, run_task
from app.assist.drafts import items_text
from app.assist.schemas import SupplierReply as ReplyAnswer
from app.config import Settings
from app.currency import convert
from app.models import (
    AuditLog,
    CustomerQuote,
    InboxEmail,
    Offer,
    PurchaseOrder,
    Rfq,
    Supplier,
    SupplierReply,
)
from app.pipeline.service import (
    PipelineError,
    _need_person,
    add_offer,
    clean_terms,
    get_request,
    items_of,
    set_lines,
)
from app.rfq.templates import ItemLine

MAX_TEXT = 20000
CURRENCIES = ("EUR", "RSD", "USD")


def _numbered(items) -> str:
    return items_text([ItemLine(i.description, i.quantity, i.part_number) for i in items])


def proposal_from(items, parsed: ReplyAnswer) -> tuple[dict, list[str]]:
    """Offer fields computed by code from the extracted lines. Returns (proposal, warnings)."""
    warnings: list[str] = []
    out = {
        "total_price": None,
        "currency": None,
        "lead_time_days": None,
        "covers_all_items": False,
        "moq_ok": True,
    }
    priced = {
        ln.item: ln
        for ln in parsed.lines
        if 1 <= ln.item <= len(items) and ln.unit_price is not None and ln.currency in CURRENCIES
    }
    currencies = {ln.currency for ln in priced.values()}
    if priced and len(currencies) == 1:
        total, leads, covers, moq_ok = 0.0, [], True, True
        for n, ln in sorted(priced.items()):
            item = items[n - 1]
            wanted = item.quantity or 0
            total += ln.unit_price * wanted
            if ln.offered_quantity is not None and ln.offered_quantity < wanted:
                covers = False
                warnings.append(f"item {n}: only {ln.offered_quantity:g} of {wanted:g} offered")
            if ln.moq is not None and wanted < ln.moq:
                moq_ok = False
                warnings.append(f"item {n}: minimum order {ln.moq:g} is above the requested {wanted:g}")
            if ln.lead_time_days is not None:
                leads.append(ln.lead_time_days)
        out.update(
            total_price=round(total, 2),
            currency=currencies.pop(),
            covers_all_items=covers and len(priced) == len(items),
            moq_ok=moq_ok,
            lead_time_days=max(leads) if leads else parsed.lead_time_days,
        )
        if len(priced) < len(items):
            warnings.append(f"{len(items) - len(priced)} item(s) have no price in the answer")
    elif priced:
        warnings.append("the prices are in different currencies: enter the total by hand")
    elif parsed.stated_total is not None and parsed.stated_currency in CURRENCIES:
        out.update(
            total_price=parsed.stated_total,
            currency=parsed.stated_currency,
            covers_all_items=True,
            lead_time_days=parsed.lead_time_days,
        )
        warnings.append("only an overall total was given: check that it covers every item")
    return out, warnings


def _needs(proposal: dict, parsed: ReplyAnswer | None) -> list[str]:
    missing = list(parsed.missing) if parsed else []
    if parsed and parsed.is_offer:
        if proposal["total_price"] is None and not any("price" in m.lower() for m in missing):
            missing.append("price")
        if proposal["lead_time_days"] is None and not any("lead" in m.lower() for m in missing):
            missing.append("lead time")
    return missing


def extract_reply(
    session: Session, settings: Settings, request_id: int, supplier_id: int, text: str, entered_by: str
) -> dict:
    by = _need_person(entered_by)
    get_request(session, request_id)
    if not text.strip():
        raise PipelineError("paste the supplier's answer first")
    if len(text) > MAX_TEXT:
        raise PipelineError(f"the text is longer than {MAX_TEXT} characters")
    sup = session.get(Supplier, supplier_id)
    sent = session.scalar(
        select(Rfq).where(Rfq.request_id == request_id, Rfq.supplier_id == supplier_id, Rfq.status == "sent")
    )
    if sup is None or sent is None:
        raise PipelineError("no letter has been sent to this supplier for this request")
    items = items_of(session, request_id)
    note = None
    parsed: ReplyAnswer | None = None
    read_by = "manual"
    if ai_enabled(settings):
        result, note = run_task(
            session,
            settings,
            "supplier_reply",
            {
                "items": "\n".join(
                    f"{n}. [{i.quantity:g}] {i.description}"
                    + (f" (part number {i.part_number})" if i.part_number else "")
                    if i.quantity is not None
                    else f"{n}. [?] {i.description}"
                    for n, i in enumerate(items, start=1)
                ),
                "received_date": datetime.now(UTC).date().isoformat(),
                "supplier_name": sup.name,
                "text": text.strip(),
            },
            ReplyAnswer,
        )
        if result is not None:
            parsed, read_by = result.parsed, result.model
    proposal = {
        "total_price": None,
        "currency": None,
        "lead_time_days": None,
        "covers_all_items": False,
        "moq_ok": True,
    }
    warnings: list[str] = []
    if parsed is not None and parsed.is_offer:
        proposal, warnings = proposal_from(items, parsed)
    elif parsed is not None:
        warnings.append("the AI did not read this as a price offer")
    missing = _needs(proposal, parsed)
    row = SupplierReply(
        request_id=request_id,
        supplier_id=supplier_id,
        text=text.strip(),
        extracted={
            "proposal": proposal,
            "valid_until": parsed.valid_until.isoformat() if parsed and parsed.valid_until else None,
            "payment_terms": parsed.payment_terms if parsed else None,
            "warranty": parsed.warranty if parsed else None,
            "notes": parsed.notes if parsed else "",
            "problems": list(parsed.problems) if parsed else [],
            "warnings": warnings,
            "is_offer": parsed.is_offer if parsed else None,
        },
        missing=missing,
        read_by=read_by,
        entered_by=by,
    )
    session.add(row)
    session.add(
        AuditLog(
            actor="human",
            actor_id=by,
            action="reply.recorded",
            payload={"request_id": request_id, "supplier_id": supplier_id, "read_by": read_by},
        )
    )
    session.commit()
    return reply_dict(row, sup.name) | {"ai": {"used": parsed is not None, "note": note}}


def reply_dict(r: SupplierReply, supplier: str) -> dict:
    return {
        "id": r.id,
        "request_id": r.request_id,
        "supplier_id": r.supplier_id,
        "supplier": supplier,
        "text": r.text,
        "status": r.status,
        "read_by": r.read_by,
        "entered_by": r.entered_by,
        "offer_id": r.offer_id,
        "missing": r.missing,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        **r.extracted,
    }


def list_replies(session: Session, request_id: int) -> list[dict]:
    names = {s.id: s.name for s in session.scalars(select(Supplier))}
    rows = session.scalars(
        select(SupplierReply).where(SupplierReply.request_id == request_id).order_by(SupplierReply.id)
    )
    return [reply_dict(r, names.get(r.supplier_id, "?")) for r in rows]


def mail_for_request(session: Session, request_id: int) -> list[dict]:
    """Supplier mail filed under this request, oldest first, with the reading of it once one exists.
    Mail without a reading is "waiting to be read"."""
    names = {s.id: s.name for s in session.scalars(select(Supplier))}
    out = []
    rows = session.scalars(
        select(InboxEmail)
        .where(InboxEmail.route == "supplier", InboxEmail.route_request_id == request_id)
        .order_by(InboxEmail.received_at, InboxEmail.id)
    )
    for e in rows:
        reply = session.get(SupplierReply, e.reply_id) if e.reply_id else None
        out.append(
            {
                "id": e.id,
                "supplier_id": e.route_supplier_id,
                "supplier": names.get(e.route_supplier_id, "?"),
                "sender": e.sender,
                "subject": e.subject,
                "body": e.body,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "how_matched": e.route_reason,
                "waiting": reply is None,
                "reply": reply_dict(reply, names.get(reply.supplier_id, "?")) if reply else None,
            }
        )
    return out


def read_mail(session: Session, settings: Settings, email_id: int, entered_by: str) -> dict:
    """Read an attached supplier mail the way a pasted answer is read: the model (if on) extracts, code adds
    up, a person confirms later. Reading the same mail twice would make two answers, so it is refused."""
    by = _need_person(entered_by)
    e = session.get(InboxEmail, email_id)
    if e is None:
        raise LookupError("mail not found")
    if e.route != "supplier" or e.route_request_id is None or e.route_supplier_id is None:
        raise PipelineError("this mail is not attached to a request and supplier yet")
    if e.reply_id is not None:
        raise PipelineError("this mail was already read: open its answer instead")
    text = f"Subject: {e.subject}\n\n{e.body}".strip()
    if not e.body.strip():
        raise PipelineError(
            "the mail has no text; if the answer is in an attachment, upload that file in the form below"
        )
    result = extract_reply(session, settings, e.route_request_id, e.route_supplier_id, text, by)
    e.reply_id = result["id"]
    session.commit()
    return result


def confirm_reply(
    session: Session,
    settings: Settings,
    reply_id: int,
    confirmed_by: str,
    total_price: float,
    currency: str,
    lead_time_days: int,
    covers_all_items: bool,
    moq_ok: bool,
    valid_until: date | None = None,
    incoterm: str | None = None,
    incoterm_place: str | None = None,
    payment_days: int | None = None,
    lines: list[dict] | None = None,
) -> Offer:
    """A person checked the numbers: only now does an offer exist."""
    by = _need_person(confirmed_by)
    reply = session.get(SupplierReply, reply_id)
    if reply is None:
        raise LookupError("reply not found")
    if reply.status != "extracted":
        raise PipelineError("this answer was already turned into an offer")
    if total_price <= 0 or lead_time_days < 0:
        raise PipelineError("the total must be above zero and the lead time cannot be negative")
    source = "manual" if reply.read_by == "manual" else "ai-reviewed"
    terms = clean_terms(valid_until, incoterm, incoterm_place, payment_days)
    existing = session.scalar(
        select(Offer).where(Offer.request_id == reply.request_id, Offer.supplier_id == reply.supplier_id)
    )
    if existing is None:
        offer = add_offer(
            session,
            settings,
            reply.request_id,
            reply.supplier_id,
            total_price,
            currency,
            lead_time_days,
            covers_all_items,
            moq_ok,
            source=source,
            lines=lines,
            **terms,
        )
    else:  # a later answer (for example after a follow-up) replaces the earlier numbers
        if session.scalar(
            select(CustomerQuote.id).where(CustomerQuote.request_id == reply.request_id).limit(1)
        ) or session.scalar(
            select(PurchaseOrder.id).where(PurchaseOrder.request_id == reply.request_id).limit(1)
        ):
            raise PipelineError(
                "a customer quote or an order already exists for this request, so the offer cannot change"
            )
        convert(1, currency, "EUR", settings)  # validates the currency
        offer = existing
        offer.total_price, offer.currency, offer.lead_time_days = total_price, currency, lead_time_days
        offer.covers_all_items, offer.moq_ok, offer.source = covers_all_items, moq_ok, source
        for name, value in terms.items():
            setattr(offer, name, value)
        if lines:
            set_lines(session, offer, lines)
    reply.status, reply.offer_id = "confirmed", offer.id
    session.add(
        AuditLog(
            actor="human",
            actor_id=by,
            action="reply.confirmed",
            payload={"reply_id": reply_id, "offer_id": offer.id, "source": source},
        )
    )
    session.commit()
    return offer
