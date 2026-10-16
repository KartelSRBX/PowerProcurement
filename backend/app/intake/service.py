from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import load_prompt, needs_human
from app.ai.base import AIAdapter
from app.config import Settings
from app.intake.mailbox import InboundEmail
from app.intake.schemas import ParsedRequest
from app.models import AuditLog, CustomerRequest

PROMPT_ID, PROMPT_VERSION = "intake", "v1"


def intake_email(
    session: Session, adapter: AIAdapter, settings: Settings, mail: InboundEmail
) -> CustomerRequest:
    """Parse one email into a request. Idempotent on Message-ID. Sends nothing anywhere."""
    existing = session.scalar(select(CustomerRequest).where(CustomerRequest.message_id == mail.message_id))
    if existing:
        return existing
    prompt = load_prompt(PROMPT_ID, PROMPT_VERSION)
    result = adapter.extract(
        prompt,
        {
            "received_date": mail.received_at.date().isoformat(),
            "sender": mail.sender,
            "subject": mail.subject,
            "body": mail.body,
        },
        ParsedRequest,
    )
    if not result.parsed.is_request:
        status = "not_request"
    elif needs_human(result, settings.ai_confidence_threshold):
        status = "needs_review"
    else:
        status = "parsed"
    row = CustomerRequest(
        message_id=mail.message_id,
        sender=mail.sender,
        subject=mail.subject,
        body=mail.body,
        received_at=mail.received_at,
        status=status,
        parsed=result.parsed.model_dump(mode="json"),
        confidence=result.parsed.confidence,
        model=result.model,
        prompt_version=f"{result.prompt_id}/{result.prompt_version}",
    )
    session.add(row)
    session.add(
        AuditLog(
            actor="system", action="request.parsed", payload={"message_id": mail.message_id, "status": status}
        )
    )
    session.commit()
    return row


def confirm_request(
    session: Session, request_id: int, confirmed_by: str, corrected: ParsedRequest | None
) -> CustomerRequest:
    """A person accepts the parsed request, optionally with corrections. Only then is it final."""
    row = session.get(CustomerRequest, request_id)
    if row is None:
        raise LookupError(request_id)
    if not confirmed_by.strip():
        raise ValueError("confirmed_by is required")
    if corrected is not None:
        row.parsed = corrected.model_dump(mode="json")
    row.status, row.confirmed_by = "confirmed", confirmed_by
    session.add(
        AuditLog(
            actor="human",
            actor_id=confirmed_by,
            action="request.confirmed",
            payload={"request_id": request_id, "corrected": corrected is not None},
        )
    )
    session.commit()
    return row
