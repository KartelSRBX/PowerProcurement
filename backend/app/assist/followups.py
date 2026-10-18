"""Step 6: follow-up letters. Code decides who needs one (no answer after N days, or an answer with gaps);
the model only drafts the wording. Follow-ups and customer reminders are ordinary letters in the
approval queue: nothing leaves until a named person approves."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assist.drafts import followup_text, reminder_text
from app.config import Settings
from app.mail.sender import MailSender, OutboundMail
from app.models import (
    AuditLog,
    CustomerQuote,
    Letter,
    Offer,
    Outcome,
    Rfq,
    Supplier,
    SupplierReply,
)
from app.pipeline.service import (
    PipelineError,
    _customer_language,
    _lines,
    _need_person,
    _ref,
    get_request,
    items_of,
)
from app.rfq.templates import pick_language

ASK_ANSWER = (
    "a quotation for the items above: unit price and currency, minimum order, lead time, "
    "payment terms and validity"
)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def candidates(
    session: Session, settings: Settings, request_id: int, silent_days: int | None = None
) -> list[dict]:
    """Suppliers that need a follow-up now, each with the list of things to ask for."""
    days = settings.followup_after_days if silent_days is None else silent_days
    now = datetime.now(UTC)
    suppliers = {s.id: s for s in session.scalars(select(Supplier))}
    sent: dict[int, Rfq] = {}
    for r in session.scalars(
        select(Rfq).where(Rfq.request_id == request_id, Rfq.status == "sent").order_by(Rfq.id)
    ):
        sent[r.supplier_id] = r
    offers = {o.supplier_id: o for o in session.scalars(select(Offer).where(Offer.request_id == request_id))}
    replies: dict[int, SupplierReply] = {}
    for r in session.scalars(
        select(SupplierReply).where(SupplierReply.request_id == request_id).order_by(SupplierReply.id)
    ):
        replies[r.supplier_id] = r
    letters = list(
        session.scalars(select(Letter).where(Letter.request_id == request_id, Letter.kind == "followup"))
    )
    out = []
    for sid, rfq in sent.items():
        sup = suppliers[sid]
        mine = [x for x in letters if x.supplier_id == sid]
        if any(x.status == "draft" for x in mine):
            continue
        offer, reply = offers.get(sid), replies.get(sid)
        needs: list[str] = []
        kind = "incomplete"
        if offer is None and reply is None:
            since = _aware(rfq.sent_at or rfq.created_at) or now
            if now - since < timedelta(days=days):
                continue
            kind, needs = "unanswered", [ASK_ANSWER]
        else:
            if reply is not None and reply.status == "extracted":
                needs += [str(m) for m in reply.missing]
            if offer is not None and not offer.covers_all_items:
                needs.append("prices for the items that are not covered")
            if offer is not None and not offer.moq_ok:
                needs.append("whether the minimum order quantity can be met for the requested quantities")
            if reply is not None and reply.status == "confirmed" and not needs:
                continue
        needs = list(dict.fromkeys(needs))
        if not needs:
            continue
        last = max(
            filter(
                None,
                [_aware(reply.created_at) if reply else None, _aware(offer.received_at) if offer else None],
            ),
            default=None,
        )
        if any(
            _aware(x.created_at) and last and _aware(x.created_at) >= last and x.status == "sent"
            for x in mine
        ):
            continue  # already asked since their last message: do not nag
        if any(x.status == "sent" for x in mine) and kind == "unanswered":
            continue
        out.append({"supplier_id": sid, "supplier": sup.name, "kind": kind, "needs": needs})
    return out


def draft_followups(
    session: Session, settings: Settings, request_id: int, silent_days: int | None = None
) -> list[Letter]:
    get_request(session, request_id)
    items = _lines(items_of(session, request_id))
    created = []
    for c in candidates(session, settings, request_id, silent_days):
        sup = session.get(Supplier, c["supplier_id"])
        lang = pick_language(sup.languages)
        subject, body, by = followup_text(
            session, settings, lang, sup.name, items, c["needs"], _ref(request_id)
        )
        why = "no answer yet" if c["kind"] == "unanswered" else "answer is incomplete"
        letter = Letter(
            request_id=request_id,
            kind="followup",
            supplier_id=sup.id,
            to_email=sup.email,
            language=lang,
            subject=subject,
            body=body,
            reason=f"{why}: {'; '.join(c['needs'])}"[:500],
            drafted_by=by,
        )
        session.add(letter)
        created.append(letter)
    session.commit()
    return created


def draft_reminder(session: Session, settings: Settings, quote_id: int) -> Letter:
    quote = session.get(CustomerQuote, quote_id)
    if quote is None:
        raise LookupError("quote not found")
    if quote.status != "sent":
        raise PipelineError("a reminder only makes sense for a quote that was sent")
    if session.scalar(select(Outcome).where(Outcome.quote_id == quote_id)) is not None:
        raise PipelineError("the customer has already answered this quote")
    if session.scalar(
        select(Letter).where(
            Letter.request_id == quote.request_id, Letter.kind == "reminder", Letter.status == "draft"
        )
    ):
        raise PipelineError("a reminder is already waiting for approval")
    req = get_request(session, quote.request_id)
    lang = _customer_language(req)
    subject, body, by = reminder_text(
        session,
        settings,
        lang,
        _lines(items_of(session, quote.request_id)),
        quote.price,
        quote.currency,
        _ref(quote.request_id),
    )
    letter = Letter(
        request_id=quote.request_id,
        kind="reminder",
        to_email=req.sender,
        language=lang,
        subject=subject,
        body=body,
        reason="the customer has not answered the quote",
        drafted_by=by,
    )
    session.add(letter)
    session.commit()
    return letter


def edit_letter(session: Session, letter_id: int, subject: str | None, body: str | None) -> Letter:
    letter = session.get(Letter, letter_id)
    if letter is None:
        raise LookupError("letter not found")
    if letter.status != "draft":
        raise PipelineError("only drafts can be edited")
    letter.subject, letter.body = subject or letter.subject, body or letter.body
    session.commit()
    return letter


def decide_letter(
    session: Session, sender: MailSender, letter_id: int, approve: bool, decided_by: str
) -> Letter:
    by = _need_person(decided_by)
    letter = session.get(Letter, letter_id)
    if letter is None:
        raise LookupError("letter not found")
    if letter.status != "draft":
        raise PipelineError(f"this letter is already {letter.status}")
    if approve:
        letter.sent_to = sender.send(
            OutboundMail(letter.to_email, letter.subject, letter.body, approved_by=by)
        )
        letter.status = "sent"
    else:
        letter.status = "rejected"
    letter.decided_by = by
    session.add(
        AuditLog(
            actor="human",
            actor_id=by,
            action=f"letter.{'approved' if approve else 'rejected'}",
            payload={"letter_id": letter_id, "kind": letter.kind},
        )
    )
    session.commit()
    return letter


def letter_dict(letter: Letter, supplier: str | None = None) -> dict:
    d = {c.name: getattr(letter, c.name) for c in letter.__table__.columns}
    d["created_at"] = letter.created_at.isoformat() if letter.created_at else None
    d["supplier"] = supplier
    return d
