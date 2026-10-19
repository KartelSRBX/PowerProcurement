"""The deal pipeline, steps 2-8. Every outward action takes a named person and goes through MailSender.
Numbers come from code. Letters come from templates, or from the model when AI is on and its text passes
the checks in app.assist.drafts; the AI-assisted steps live in app.assist."""

import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assist.drafts import invoice_text, quote_text, rfq_text
from app.assist.pool import augment_shortlist
from app.config import Settings
from app.currency import convert, to_eur
from app.intake.schemas import ParsedRequest
from app.intake.service import sync_items
from app.legal.service import blocker as legal_blocker
from app.mail.sender import MailSender, OutboundMail
from app.models import (
    AuditLog,
    CustomerQuote,
    CustomerRequest,
    MarketPrice,
    Offer,
    Outcome,
    PriceEvent,
    PurchaseOrder,
    RequestItem,
    Rfq,
    ShortlistEntry,
    Supplier,
)
from app.orders.templates import po_letter
from app.pricing.service import fetch_target_prices, target_total_eur
from app.rfq.templates import ItemLine, pick_language
from app.scoring.scoring import OfferFacts, SupplierFacts, Weights, landed_cost, score_offers
from app.suppliers.shortlist import build_shortlist, catalog_lines_for


class PipelineError(Exception):
    """A step cannot run yet; the message says what is missing."""


def _audit(session: Session, actor: str, actor_id: str | None, action: str, **payload) -> None:
    session.add(AuditLog(actor=actor, actor_id=actor_id, action=action, payload=payload))


def _need_person(name: str) -> str:
    if not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def get_request(session: Session, request_id: int) -> CustomerRequest:
    row = session.get(CustomerRequest, request_id)
    if row is None:
        raise LookupError(f"request {request_id} not found")
    return row


def items_of(session: Session, request_id: int) -> list[RequestItem]:
    return list(
        session.scalars(
            select(RequestItem).where(RequestItem.request_id == request_id).order_by(RequestItem.id)
        )
    )


def _lines(items: list[RequestItem]) -> list[ItemLine]:
    return [ItemLine(i.description, i.quantity, i.part_number) for i in items]


def _ref(request_id: int) -> str:
    return f"PP-{request_id:05d}"


def _customer_language(req: CustomerRequest) -> str:
    return req.parsed.get("language") if req.parsed.get("language") in ("sr", "en") else "en"


# ---- Step 1b: a request entered without AI ---------------------------------------------------


def create_manual_request(
    session: Session,
    sender: str,
    subject: str,
    body: str,
    parsed: ParsedRequest,
    confirmed_by: str,
    message_id: str | None = None,
) -> CustomerRequest:
    by = _need_person(confirmed_by)
    stamp = datetime.now().astimezone()
    if message_id and session.scalar(select(CustomerRequest).where(CustomerRequest.message_id == message_id)):
        raise PipelineError("a request for this email already exists")
    row = CustomerRequest(
        message_id=message_id or f"manual-{stamp.timestamp():.6f}",
        sender=sender,
        subject=subject,
        body=body,
        received_at=stamp,
        status="confirmed",
        parsed=parsed.model_dump(mode="json"),
        confidence=1.0,
        model="manual",
        prompt_version="manual",
        confirmed_by=by,
    )
    session.add(row)
    session.flush()
    sync_items(session, row)
    _audit(session, "human", by, "request.created_manually", request_id=row.id)
    session.commit()
    return row


# ---- Steps 2-3 --------------------------------------------------------------------------------


def run_discovery(session: Session, settings: Settings, request_id: int) -> dict:
    req = get_request(session, request_id)
    if req.status != "confirmed":
        raise PipelineError("the request must be confirmed by a person first")
    items = items_of(session, request_id)
    if not items or any(i.quantity is None for i in items):
        raise PipelineError("every item needs a quantity before suppliers and prices can be looked up")
    shortlist = build_shortlist(session, req)
    ai = augment_shortlist(session, settings, req, items)
    targets = fetch_target_prices(session, settings, request_id)
    return {
        "ai": ai,
        "shortlist": len(shortlist),
        "items_with_target": sum(v is not None for v in targets.values()),
        "target_total_eur": target_total_eur(session, request_id, targets),
    }


def set_supplier_selected(session: Session, request_id: int, supplier_id: int, selected: bool) -> None:
    entry = session.scalar(
        select(ShortlistEntry).where(
            ShortlistEntry.request_id == request_id, ShortlistEntry.supplier_id == supplier_id
        )
    )
    if entry is None:
        raise LookupError("supplier is not on this shortlist")
    entry.selected = selected
    session.commit()


# ---- Step 4: RFQ drafts and the approval queue ------------------------------------------------


def draft_rfqs(session: Session, settings: Settings, request_id: int) -> list[Rfq]:
    req = get_request(session, request_id)
    items = items_of(session, request_id)
    existing = {r.supplier_id for r in session.scalars(select(Rfq).where(Rfq.request_id == request_id))}
    chosen = session.scalars(
        select(ShortlistEntry).where(
            ShortlistEntry.request_id == request_id, ShortlistEntry.selected.is_(True)
        )
    )
    created = []
    for entry in chosen:
        if entry.supplier_id in existing:
            continue
        sup = session.get(Supplier, entry.supplier_id)
        lang = pick_language(sup.languages)
        subject, body, drafted_by = rfq_text(
            session, settings, lang, sup.name, _lines(items), req.parsed.get("needed_by"), _ref(request_id)
        )
        rfq = Rfq(
            request_id=request_id,
            supplier_id=sup.id,
            language=lang,
            subject=subject,
            body=body,
            drafted_by=drafted_by,
        )
        session.add(rfq)
        created.append(rfq)
    if not created and not existing:
        raise PipelineError("no suppliers are selected; run discovery and select at least one")
    session.commit()
    return created


def edit_rfq(session: Session, rfq_id: int, subject: str | None, body: str | None) -> Rfq:
    rfq = session.get(Rfq, rfq_id)
    if rfq is None:
        raise LookupError("rfq not found")
    if rfq.status != "draft":
        raise PipelineError("only drafts can be edited")
    rfq.subject, rfq.body = subject or rfq.subject, body or rfq.body
    session.commit()
    return rfq


def claim_draft(session: Session, model, row_id: int) -> None:
    """Take a draft out of 'draft' before sending, so two clicks or requests cannot both send it."""
    taken = session.execute(
        update(model).where(model.id == row_id, model.status == "draft").values(status="sending")
    )
    session.commit()
    if taken.rowcount != 1:
        raise PipelineError("this letter is already being handled")


def release_draft(session: Session, row) -> None:
    """The send failed: put the draft back so the person can try again."""
    session.rollback()
    session.execute(update(type(row)).where(type(row).id == row.id).values(status="draft"))
    session.commit()


def send_claimed(session: Session, sender: MailSender, row, mail: OutboundMail) -> str:
    try:
        return sender.send(mail)
    except Exception:
        release_draft(session, row)
        raise


def decide_rfq(session: Session, sender: MailSender, rfq_id: int, approve: bool, decided_by: str) -> Rfq:
    by = _need_person(decided_by)
    rfq = session.get(Rfq, rfq_id)
    if rfq is None:
        raise LookupError("rfq not found")
    if rfq.status != "draft":
        raise PipelineError(f"this letter is already {rfq.status}")
    claim_draft(session, Rfq, rfq_id)
    session.refresh(rfq)
    if approve:
        sup = session.get(Supplier, rfq.supplier_id)
        rfq.sent_to = send_claimed(
            session, sender, rfq, OutboundMail(sup.email, rfq.subject, rfq.body, approved_by=by)
        )
        rfq.status = "sent"
        rfq.sent_at = datetime.now(UTC)
    else:
        rfq.status = "rejected"
    rfq.decided_by = by
    _audit(session, "human", by, "rfq.approved" if approve else "rfq.rejected", rfq_id=rfq_id)
    session.commit()
    return rfq


# ---- Step 5: offers and scoring -----------------------------------------------------------------


def add_offer(
    session: Session,
    settings: Settings,
    request_id: int,
    supplier_id: int,
    total_price: float,
    currency: str,
    lead_time_days: int,
    covers_all_items: bool,
    moq_ok: bool,
    source: str = "manual",
) -> Offer:
    convert(1, currency, "EUR", settings)  # validates the currency
    offer = Offer(
        request_id=request_id,
        supplier_id=supplier_id,
        total_price=total_price,
        currency=currency,
        lead_time_days=lead_time_days,
        covers_all_items=covers_all_items,
        moq_ok=moq_ok,
        source=source,
    )
    session.add(offer)
    session.commit()
    return offer


def simulate_offers(session: Session, settings: Settings, request_id: int) -> list[Offer]:
    """DEMO ONLY: stands in for suppliers answering, using their synthetic price lists plus a small
    deterministic wobble. Real answers are entered by a person (and later extracted by AI)."""
    items = items_of(session, request_id)
    sent = list(session.scalars(select(Rfq).where(Rfq.request_id == request_id, Rfq.status == "sent")))
    if not sent:
        raise PipelineError("no letter has been sent yet, so there is nobody to answer")
    have = {o.supplier_id for o in session.scalars(select(Offer).where(Offer.request_id == request_id))}
    out = []
    for rfq in sent:
        if rfq.supplier_id in have:
            continue
        lines = [
            [c for c in catalog_lines_for(session, i) if c.supplier_id == rfq.supplier_id] for i in items
        ]
        covered = all(lines)
        total, lead, moq_ok, currency = 0.0, 0, True, "EUR"
        wobble = (
            0.97
            + (int(hashlib.sha256(f"{request_id}{rfq.supplier_id}".encode()).hexdigest()[:4], 16) % 12) / 100
        )
        for item, cs in zip(items, lines, strict=True):
            if not cs:
                continue
            c = cs[0]
            currency = c.currency
            total += (item.quantity or 0) * c.unit_price * wobble
            lead = max(lead, c.lead_time_days)
            moq_ok = moq_ok and (item.quantity or 0) >= c.moq
        if total == 0:
            continue
        out.append(
            add_offer(
                session,
                settings,
                request_id,
                rfq.supplier_id,
                round(total, 2),
                currency,
                lead,
                covered,
                moq_ok,
                source="demo-simulator",
            )
        )
    return out


def _days_available(req: CustomerRequest, today: date) -> int | None:
    needed = req.parsed.get("needed_by")
    return None if not needed else (date.fromisoformat(needed) - today).days


def score_request(
    session: Session, settings: Settings, request_id: int, weights: Weights, today: date | None = None
) -> list[dict]:
    req = get_request(session, request_id)
    today = today or date.today()
    offers = list(session.scalars(select(Offer).where(Offer.request_id == request_id)))
    if not offers:
        raise PipelineError("there are no offers to compare yet")
    pairs, by_offer = [], {}
    for o in offers:
        sup = session.get(Supplier, o.supplier_id)
        landed = landed_cost(to_eur(o.total_price, o.currency, settings), sup.country)
        by_offer[o.id] = (o, sup, landed)
        pairs.append(
            (
                OfferFacts(o.id, sup.id, landed, o.lead_time_days, o.covers_all_items, o.moq_ok),
                SupplierFacts(
                    sup.country,
                    sup.age_years,
                    sup.vat_verified,
                    sup.deals_count,
                    sup.framework_contract,
                    sup.payment_terms_days,
                    sup.warranty_months,
                    sup.sanctioned,
                    sup.flags,
                ),
            )
        )
    items = items_of(session, request_id)
    targets = {i.id: _median_target(session, i, settings) for i in items}
    target = target_total_eur(session, request_id, targets)
    results = score_offers(pairs, target, _days_available(req, today), weights)
    out = []
    for r in results:
        o, sup, landed = by_offer[r.offer_id]
        out.append(
            {
                "offer_id": o.id,
                "supplier": sup.name,
                "country": sup.country,
                "excluded": r.excluded,
                "total": r.total,
                "scores": {k: round(v, 1) for k, v in r.scores.items()},
                "flags": r.notes,
                "offer_total": o.total_price,
                "currency": o.currency,
                "landed_cost_eur": round(landed, 2),
                "lead_time_days": o.lead_time_days,
                "offer_source": o.source,
            }
        )
    return out


def _median_target(session: Session, item: RequestItem, settings: Settings) -> float | None:
    rows = list(session.scalars(select(MarketPrice).where(MarketPrice.request_item_id == item.id)))
    if not rows:
        return None
    vals = sorted(to_eur(r.unit_price, r.currency, settings) for r in rows)
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


# ---- Step 6: customer quote -------------------------------------------------------------------


def create_quote(
    session: Session,
    settings: Settings,
    request_id: int,
    offer_id: int,
    markup: float | None,
    currency: str,
    created_by: str,
) -> CustomerQuote:
    by = _need_person(created_by)
    req = get_request(session, request_id)
    offer = session.get(Offer, offer_id)
    if offer is None or offer.request_id != request_id:
        raise LookupError("offer not found for this request")
    sup = session.get(Supplier, offer.supplier_id)
    if sup.sanctioned or not offer.covers_all_items:
        raise PipelineError("this offer is excluded by a hard filter and cannot be quoted")
    markup = settings.default_markup if markup is None else markup
    if markup <= -1:
        raise PipelineError("markup must be greater than -100%")
    cost_eur = landed_cost(to_eur(offer.total_price, offer.currency, settings), sup.country)
    price = convert(cost_eur * (1 + markup), "EUR", currency, settings)
    lang = _customer_language(req)
    subject, body, drafted_by = quote_text(
        session,
        settings,
        lang,
        _lines(items_of(session, request_id)),
        price,
        currency,
        offer.lead_time_days,
        _ref(request_id),
    )
    quote = CustomerQuote(
        request_id=request_id,
        offer_id=offer_id,
        cost_eur=round(cost_eur, 2),
        markup=markup,
        currency=currency,
        price=round(price, 2),
        language=lang,
        subject=subject,
        body=body,
        drafted_by=drafted_by,
    )
    session.add(quote)
    session.add(
        PriceEvent(
            request_id=request_id,
            kind="supplier_cost",
            amount=round(cost_eur, 2),
            currency="EUR",
            actor="system",
        )
    )
    session.add(
        PriceEvent(
            request_id=request_id,
            kind="quote_draft",
            amount=round(price, 2),
            currency=currency,
            actor="human",
            actor_id=by,
        )
    )
    session.commit()
    return quote


def decide_quote(
    session: Session, sender: MailSender, quote_id: int, approve: bool, decided_by: str
) -> CustomerQuote:
    by = _need_person(decided_by)
    quote = session.get(CustomerQuote, quote_id)
    if quote is None:
        raise LookupError("quote not found")
    if quote.status != "draft":
        raise PipelineError(f"this quote is already {quote.status}")
    req = get_request(session, quote.request_id)
    claim_draft(session, CustomerQuote, quote_id)
    session.refresh(quote)
    if approve:
        quote.sent_to = send_claimed(
            session, sender, quote, OutboundMail(req.sender, quote.subject, quote.body, approved_by=by)
        )
        quote.status = "sent"
        session.add(
            PriceEvent(
                request_id=quote.request_id,
                kind="quote_sent",
                amount=quote.price,
                currency=quote.currency,
                actor="human",
                actor_id=by,
            )
        )
    else:
        quote.status = "rejected"
    quote.decided_by = by
    _audit(session, "human", by, "quote.approved" if approve else "quote.rejected", quote_id=quote_id)
    session.commit()
    return quote


# ---- Step 7: outcome ----------------------------------------------------------------------------


def record_outcome(
    session: Session,
    quote_id: int,
    kind: str,
    price: float | None,
    currency: str | None,
    reason: str | None,
    confirmed_by: str,
) -> Outcome:
    by = _need_person(confirmed_by)
    if kind not in ("accepted", "counter", "rejected", "silence"):
        raise PipelineError("outcome must be accepted, counter, rejected or silence")
    quote = session.get(CustomerQuote, quote_id)
    if quote is None:
        raise LookupError("quote not found")
    if quote.status != "sent":
        raise PipelineError("an outcome can only be recorded for a quote that was sent")
    if kind == "counter" and price is None:
        raise PipelineError("a counter-offer needs the price the customer named")
    outcome = Outcome(
        quote_id=quote_id,
        kind=kind,
        price=price,
        currency=currency or (quote.currency if price else None),
        reason=reason,
        confirmed_by=by,
    )
    session.add(outcome)
    if price is not None:
        session.add(
            PriceEvent(
                request_id=quote.request_id,
                kind=f"client_{kind}",
                amount=price,
                currency=outcome.currency,
                actor="client",
                actor_id=None,
            )
        )
    _audit(session, "human", by, "outcome.recorded", quote_id=quote_id, kind=kind)
    session.commit()
    return outcome


# ---- Step 8: purchase order and invoice request -----------------------------------------------------


def create_po(
    session: Session, sender: MailSender, settings: Settings, request_id: int, approved_by: str
) -> PurchaseOrder:
    by = _need_person(approved_by)
    quote = session.scalar(
        select(CustomerQuote)
        .where(CustomerQuote.request_id == request_id, CustomerQuote.status == "sent")
        .order_by(CustomerQuote.id.desc())
    )
    if quote is None:
        raise PipelineError("no quote has been sent to the customer")
    outcome = session.scalar(select(Outcome).where(Outcome.quote_id == quote.id).order_by(Outcome.id.desc()))
    if outcome is None or outcome.kind != "accepted":
        raise PipelineError(
            "the customer has not accepted: a purchase order is only created after their decision"
        )
    if session.scalar(select(PurchaseOrder).where(PurchaseOrder.request_id == request_id)) is not None:
        raise PipelineError("a purchase order already exists for this request")
    offer = session.get(Offer, quote.offer_id)
    sup = session.get(Supplier, offer.supplier_id)
    cost_eur = landed_cost(to_eur(offer.total_price, offer.currency, settings), sup.country)
    agreed = outcome.price if outcome.price is not None else quote.price
    agreed_eur = to_eur(agreed, outcome.currency or quote.currency, settings)
    checks = {
        "within_po_limit": cost_eur <= settings.po_budget_limit_eur,
        "po_limit_eur": settings.po_budget_limit_eur,
        "cost_eur": round(cost_eur, 2),
        "agreed_price_eur": round(agreed_eur, 2),
        "not_below_cost": agreed_eur >= cost_eur,
    }
    failed = [k for k in ("within_po_limit", "not_below_cost") if not checks[k]]
    if failed:
        raise PipelineError(f"budget check failed: {', '.join(failed)} ({checks})")
    held = legal_blocker(session, request_id)
    if held:
        raise PipelineError(f"legal sign-off is required: {held}")
    req = get_request(session, request_id)
    subject, body = po_letter(
        pick_language(sup.languages),
        sup.name,
        _lines(items_of(session, request_id)),
        offer.total_price,
        offer.currency,
        _ref(request_id),
    )
    po = PurchaseOrder(
        request_id=request_id,
        offer_id=offer.id,
        supplier_id=sup.id,
        total_eur=round(cost_eur, 2),
        budget_checks=checks,
        status="sent",
        approved_by=by,
    )
    session.add(po)
    try:
        session.flush()  # a second order for the same request fails here, before any mail is sent
    except IntegrityError as exc:
        session.rollback()
        raise PipelineError("a purchase order already exists for this request") from exc
    sender.send(OutboundMail(sup.email, subject, body, approved_by=by))
    _audit(session, "human", by, "po.approved", request_id=req.id, checks=checks)
    session.commit()
    return po


def invoice_draft(session: Session, settings: Settings, po_id: int) -> dict:
    """The invoice-request letter as it would be sent, for a person to read and edit first."""
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        raise LookupError("purchase order not found")
    sup = session.get(Supplier, po.supplier_id)
    offer = session.get(Offer, po.offer_id)
    subject, body, drafted_by = invoice_text(
        session,
        settings,
        pick_language(sup.languages),
        sup.name,
        _lines(items_of(session, po.request_id)),
        f"{offer.total_price:,.2f} {offer.currency}",
        _ref(po.request_id),
    )
    return {"to": f"{sup.name} <{sup.email}>", "subject": subject, "body": body, "drafted_by": drafted_by}


def request_invoice(
    session: Session,
    sender: MailSender,
    po_id: int,
    approved_by: str,
    settings: Settings | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> PurchaseOrder:
    by = _need_person(approved_by)
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        raise LookupError("purchase order not found")
    if po.invoice_requested_by:
        raise PipelineError("the invoice has already been requested")
    sup = session.get(Supplier, po.supplier_id)
    if (subject is None) != (body is None):
        raise PipelineError("send the subject and the text together")
    if subject is None:
        draft = invoice_draft(session, settings or Settings(_env_file=None), po_id)
        subject, body = draft["subject"], draft["body"]
    if not (subject.strip() and body.strip()):
        raise PipelineError("the subject and the text of the letter cannot be empty")
    taken = session.execute(
        update(PurchaseOrder)
        .where(PurchaseOrder.id == po_id, PurchaseOrder.invoice_requested_by.is_(None))
        .values(invoice_requested_by=by)
    )
    session.commit()
    if taken.rowcount != 1:
        raise PipelineError("the invoice has already been requested")
    try:
        sender.send(OutboundMail(sup.email, subject, body, approved_by=by))
    except Exception:
        session.rollback()
        session.execute(
            update(PurchaseOrder).where(PurchaseOrder.id == po_id).values(invoice_requested_by=None)
        )
        session.commit()
        raise
    session.refresh(po)
    _audit(session, "human", by, "invoice.requested", po_id=po_id)
    session.commit()
    return po


# ---- Where is this request? -----------------------------------------------------------------------------


def stage_of(session: Session, request_id: int) -> dict:
    req = get_request(session, request_id)
    q = lambda model: session.scalar(select(model).where(model.request_id == request_id).limit(1))  # noqa: E731
    rfqs = list(session.scalars(select(Rfq).where(Rfq.request_id == request_id)))
    quotes = list(session.scalars(select(CustomerQuote).where(CustomerQuote.request_id == request_id)))
    po = q(PurchaseOrder)
    if req.status != "confirmed":
        stage, nxt = "intake", "a person confirms the parsed request"
    elif po is not None:
        stage, nxt = (
            ("invoice_requested", "done") if po.invoice_requested_by else ("ordered", "request the invoice")
        )
    elif quotes:
        sent = [x for x in quotes if x.status == "sent"]
        stage, nxt = (
            ("quote_sent", "record the customer's answer")
            if sent
            else ("quote_draft", "approve or reject the quote")
        )
    elif q(Offer) is not None:
        stage, nxt = "offers_in", "score offers and create the customer quote"
    elif any(r.status == "sent" for r in rfqs):
        stage, nxt = "rfq_sent", "enter supplier answers"
    elif rfqs:
        stage, nxt = "rfq_drafts", "approve or reject the supplier letters"
    elif q(ShortlistEntry) is not None:
        stage, nxt = "shortlisted", "draft supplier letters"
    else:
        stage, nxt = "confirmed", "run supplier and price discovery"
    return {"request_id": request_id, "stage": stage, "next": nxt}
