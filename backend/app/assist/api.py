import base64
import binascii
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assist import files, followups, insight, replies
from app.config import Settings, get_settings
from app.db import get_session
from app.mail.sender import MailSender
from app.models import Letter, Supplier
from app.pipeline.api import LineIn, WeightsIn, _dump, get_sender, guarded
from app.pipeline.service import PipelineError
from app.scoring.scoring import Weights

router = APIRouter(tags=["assist"])


class ReplyIn(BaseModel):
    supplier_id: int
    text: str
    entered_by: str


class ReplyFileIn(BaseModel):
    supplier_id: int
    filename: str
    content_base64: str
    entered_by: str


class ConfirmIn(BaseModel):
    confirmed_by: str
    total_price: float
    currency: str
    lead_time_days: int
    covers_all_items: bool = True
    moq_ok: bool = True
    valid_until: date | None = None
    incoterm: str | None = None
    incoterm_place: str | None = None
    payment_days: int | None = None
    lines: list[LineIn] | None = None


class FollowupIn(BaseModel):
    silent_days: int | None = None


class CustomerTextIn(BaseModel):
    text: str


class NarrativeIn(BaseModel):
    topic: str
    days: int = 30
    customer: str | None = None
    category: str | None = None


class ParseIn(BaseModel):
    limit: int = 20


class LetterEditIn(BaseModel):
    subject: str | None = None
    body: str | None = None


class LetterDecisionIn(BaseModel):
    approve: bool
    decided_by: str


@router.post("/requests/{request_id}/replies")
def add_reply(
    request_id: int,
    body: ReplyIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(
        replies.extract_reply, session, settings, request_id, body.supplier_id, body.text, body.entered_by
    )


@router.post("/requests/{request_id}/replies/file")
def add_reply_file(
    request_id: int,
    body: ReplyFileIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    def read():
        if len(body.content_base64) > files.MAX_BYTES * 4 // 3 + 16:
            raise PipelineError(f"the file is larger than {files.MAX_BYTES // 1_000_000} MB")
        try:
            data = base64.b64decode(body.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PipelineError("the file could not be decoded") from exc
        text = files.extract_text(body.filename, data)
        return replies.extract_reply(session, settings, request_id, body.supplier_id, text, body.entered_by)

    return guarded(read)


@router.get("/requests/{request_id}/replies")
def list_replies(request_id: int, session: Session = Depends(get_session)):
    return replies.list_replies(session, request_id)


@router.post("/replies/{reply_id}/confirm")
def confirm_reply(
    reply_id: int,
    body: ConfirmIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return _dump(guarded(replies.confirm_reply, session, settings, reply_id, **body.model_dump()))


@router.post("/requests/{request_id}/score/explain")
def explain(
    request_id: int,
    body: WeightsIn | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    w = Weights(**(body.model_dump() if body else {}))
    return guarded(insight.explain_scores, session, settings, request_id, w)


@router.get("/requests/{request_id}/followups")
def followup_candidates(
    request_id: int,
    silent_days: int | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(followups.candidates, session, settings, request_id, silent_days)


@router.post("/requests/{request_id}/followups")
def draft_followups(
    request_id: int,
    body: FollowupIn | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    created = guarded(
        followups.draft_followups, session, settings, request_id, body.silent_days if body else None
    )
    return [followups.letter_dict(x, session.get(Supplier, x.supplier_id).name) for x in created]


@router.get("/requests/{request_id}/letters")
def list_letters(request_id: int, session: Session = Depends(get_session)):
    names = {s.id: s.name for s in session.scalars(select(Supplier))}
    rows = session.scalars(select(Letter).where(Letter.request_id == request_id).order_by(Letter.id))
    return [followups.letter_dict(x, names.get(x.supplier_id)) for x in rows]


@router.patch("/letters/{letter_id}")
def edit_letter(letter_id: int, body: LetterEditIn, session: Session = Depends(get_session)):
    return followups.letter_dict(guarded(followups.edit_letter, session, letter_id, body.subject, body.body))


@router.post("/letters/{letter_id}/decision")
def decide_letter(
    letter_id: int,
    body: LetterDecisionIn,
    session: Session = Depends(get_session),
    sender: MailSender = Depends(get_sender),
):
    return followups.letter_dict(
        guarded(followups.decide_letter, session, sender, letter_id, body.approve, body.decided_by)
    )


@router.post("/quotes/{quote_id}/reminder")
def reminder(
    quote_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return followups.letter_dict(guarded(followups.draft_reminder, session, settings, quote_id))


@router.post("/orders/{po_id}/customer-confirmation")
def customer_confirmation(
    po_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return followups.letter_dict(guarded(followups.draft_order_confirmation, session, settings, po_id))


@router.post("/orders/{po_id}/delivery-question")
def delivery_question(
    po_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    letter = guarded(followups.draft_delivery_question, session, settings, po_id)
    return followups.letter_dict(letter, session.get(Supplier, letter.supplier_id).name)


@router.post("/quotes/{quote_id}/customer-reply/read")
def read_customer_reply(
    quote_id: int,
    body: CustomerTextIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(insight.read_customer_answer, session, settings, quote_id, body.text)


@router.post("/analytics/narrative")
def narrative(
    body: NarrativeIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(insight.narrative, session, settings, body.topic, body.days, body.customer, body.category)


@router.post("/mail/parse-all")
def parse_all(
    body: ParseIn | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(insight.parse_inbox, session, settings, body.limit if body else 20)
