"""Which of the arriving mails are supplier answers, and to which of our letters. A reply is matched, in
order of strength, by the Message-ID of the letter it answers, by the request number in its subject
(PP-00012) together with the sender's address, or by the sender alone when only one request is waiting
for that supplier. Anything doubtful goes to the "unattached" list for a person; nothing is guessed
silently, and nothing here sends mail or creates an offer."""

import re
from dataclasses import dataclass
from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InboxEmail, Offer, Rfq, Supplier

REF = re.compile(r"\bPP-(\d{5})\b", re.I)
RFQ_ID = re.compile(r"<pp-rfq-(\d+)@", re.I)


def rfq_message_id(rfq_id: int) -> str:
    """The Message-ID given to the letter of one RFQ, so that a reply can point back at it."""
    return f"<pp-rfq-{rfq_id}@powerprocurement.local>"


@dataclass(frozen=True)
class Route:
    kind: str  # customer | supplier | unattached
    request_id: int | None = None
    supplier_id: int | None = None
    reason: str = ""


def _address(sender: str) -> str:
    return parseaddr(sender)[1].strip().lower()


def route_email(session: Session, mail) -> Route:
    suppliers = list(session.scalars(select(Supplier)))
    sender = _address(mail.sender)
    known = next((s for s in suppliers if s.email.strip().lower() == sender), None)
    sent = list(session.scalars(select(Rfq).where(Rfq.status == "sent")))

    # 1. a reply to one of our letters says so in its headers
    for text in (mail.in_reply_to, mail.references):
        for m in RFQ_ID.finditer(text or ""):
            rfq = next((r for r in sent if r.id == int(m.group(1))), None)
            if rfq:
                return Route("supplier", rfq.request_id, rfq.supplier_id, "answers our letter (mail headers)")

    # 2. the request number in the subject
    ref = REF.search(mail.subject or "")
    if ref:
        request_id = int(ref.group(1))
        asked = [r for r in sent if r.request_id == request_id]
        if not asked:
            return Route(
                "unattached",
                None,
                known.id if known else None,
                f"request number PP-{request_id:05d} found, but no letter for it was sent",
            )
        match = next((r for r in asked if known and r.supplier_id == known.id), None)
        if match:
            return Route(
                "supplier",
                request_id,
                match.supplier_id,
                f"request number PP-{request_id:05d} in the subject, sender is the supplier asked",
            )
        return Route(
            "unattached",
            request_id,
            None,
            f"request number PP-{request_id:05d} found, but the sender is not a supplier asked about it",
        )

    # 3. no request number: a known supplier with exactly one request still waiting for its answer
    if known:
        answered = {(o.request_id, o.supplier_id) for o in session.scalars(select(Offer))}
        waiting = [
            r for r in sent if r.supplier_id == known.id and (r.request_id, r.supplier_id) not in answered
        ]
        if len(waiting) == 1:
            return Route(
                "supplier",
                waiting[0].request_id,
                known.id,
                "only one request is waiting for this supplier's answer",
            )
        if waiting:
            return Route(
                "unattached",
                None,
                known.id,
                f"{known.name} has {len(waiting)} requests waiting and the subject has no request number",
            )
        return Route("unattached", None, known.id, f"{known.name} has no request waiting for an answer")
    return Route("customer")


def apply_route(session: Session, row: InboxEmail, route: Route, by: str = "auto") -> InboxEmail:
    row.route, row.route_request_id, row.route_supplier_id = route.kind, route.request_id, route.supplier_id
    row.route_reason, row.routed_by = route.reason[:300], by
    session.commit()
    return row
