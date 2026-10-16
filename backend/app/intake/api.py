from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import make_adapter
from app.ai.replay import RecordingNotFound
from app.config import Settings, get_settings
from app.db import get_session
from app.intake.mailbox import InboundEmail
from app.intake.schemas import ParsedRequest
from app.intake.service import confirm_request, intake_email
from app.models import CustomerRequest

router = APIRouter(prefix="/requests", tags=["requests"])


class IntakeIn(BaseModel):
    message_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime | None = None


class ConfirmIn(BaseModel):
    confirmed_by: str
    corrected: ParsedRequest | None = None


def _out(r: CustomerRequest) -> dict:
    return {
        "id": r.id,
        "status": r.status,
        "sender": r.sender,
        "subject": r.subject,
        "confidence": r.confidence,
        "parsed": r.parsed,
        "model": r.model,
        "prompt_version": r.prompt_version,
        "confirmed_by": r.confirmed_by,
    }


@router.post("/intake")
def intake(
    body: IntakeIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    mail = InboundEmail(
        body.message_id, body.sender, body.subject, body.body, body.received_at or datetime.now(UTC)
    )
    try:
        return _out(intake_email(session, make_adapter(settings), settings, mail))
    except RecordingNotFound as exc:
        raise HTTPException(409, f"AI_PROVIDER=mock has no recorded answer for this email: {exc}") from exc


@router.get("")
def list_requests(session: Session = Depends(get_session)):
    rows = session.scalars(select(CustomerRequest).order_by(CustomerRequest.id.desc()).limit(100))
    return [_out(r) for r in rows]


@router.post("/{request_id}/confirm")
def confirm(request_id: int, body: ConfirmIn, session: Session = Depends(get_session)):
    try:
        return _out(confirm_request(session, request_id, body.confirmed_by, body.corrected))
    except LookupError as exc:
        raise HTTPException(404, "request not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
