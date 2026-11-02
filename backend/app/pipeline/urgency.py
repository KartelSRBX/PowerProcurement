"""Request urgency. A person marks a request urgent and says by when the customer has to get a quote;
the board lists what is still waiting for that answer. The code never guesses urgency from the mail text
and changes no score, price or letter: it only keeps the flag and the date, and counts days.

A request is answered once a quote has been sent (stage quote_sent or later); until then it is open.
The customer's own "needed by" date from the mail is shown beside it for context and is not the
reply-by date."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditLog, CustomerRequest
from app.pipeline.service import PipelineError, get_request, stage_of

ANSWERED = {"quote_sent", "ordered", "invoice_requested"}
ORDER = {"overdue": 0, "today": 1, "soon": 2, "later": 3, "no_date": 4}


def _person(name: str) -> str:
    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _needed_by(req: CustomerRequest) -> date | None:
    raw = (req.parsed or {}).get("needed_by")
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _state(respond_by: date | None, today: date, warn_days: int) -> tuple[str, int | None]:
    if respond_by is None:
        return "no_date", None
    days = (respond_by - today).days
    if days < 0:
        return "overdue", days
    if days == 0:
        return "today", 0
    return ("soon" if days <= warn_days else "later"), days


def describe(req: CustomerRequest, settings: Settings, today: date | None = None) -> dict:
    today = today or date.today()
    state, days = _state(req.respond_by, today, settings.urgency_warn_days)
    needed = _needed_by(req)
    return {
        "urgent": req.urgent,
        "respond_by": req.respond_by.isoformat() if req.respond_by else None,
        "state": state,
        "days_left": days,
        "note": req.urgency_note,
        "set_by": req.urgency_by,
        "needed_by": needed.isoformat() if needed else None,
        "needed_in_days": (needed - today).days if needed else None,
    }


def set_urgency(
    session: Session,
    request_id: int,
    changed_by: str,
    urgent: bool,
    respond_by: date | None,
    note: str = "",
) -> CustomerRequest:
    who = _person(changed_by)
    req = get_request(session, request_id)
    if req.status == "not_request":
        raise PipelineError("this mail was marked as not a request")
    note = note.strip()
    if respond_by is not None and respond_by != req.respond_by and respond_by < date.today():
        raise ValueError("the reply-by date cannot be in the past")
    before = {"urgent": req.urgent, "respond_by": str(req.respond_by), "note": req.urgency_note}
    req.urgent, req.respond_by = urgent, respond_by
    req.urgency_note, req.urgency_by = note[:300] or None, who
    session.add(
        AuditLog(
            actor="human",
            actor_id=who,
            action="request.urgency",
            payload={
                "request_id": request_id,
                "before": before,
                "after": {"urgent": urgent, "respond_by": str(respond_by), "note": note[:300] or None},
            },
        )
    )
    session.commit()
    return req


def board(session: Session, settings: Settings, today: date | None = None) -> dict:
    """Open requests that are urgent or carry a reply-by date: overdue first, then today, then the rest."""
    today = today or date.today()
    rows = session.scalars(
        select(CustomerRequest)
        .where(CustomerRequest.status != "not_request")
        .where((CustomerRequest.urgent.is_(True)) | (CustomerRequest.respond_by.is_not(None)))
        .order_by(CustomerRequest.id)
    )
    items = []
    for r in rows:
        stage = stage_of(session, r.id)
        if stage["stage"] in ANSWERED:
            continue
        d = describe(r, settings, today)
        items.append(
            {
                "request_id": r.id,
                "subject": r.subject,
                "sender": r.sender,
                "stage": stage["stage"],
                "next": stage["next"],
                **d,
            }
        )
    items.sort(
        key=lambda i: (
            ORDER[i["state"]] if i["state"] != "no_date" or not i["urgent"] else 1.5,
            i["days_left"] if i["days_left"] is not None else 0,
            i["request_id"],
        )
    )
    return {
        "items": items,
        "counts": {
            "overdue": sum(1 for i in items if i["state"] == "overdue"),
            "today": sum(1 for i in items if i["state"] == "today"),
            "urgent": sum(1 for i in items if i["urgent"]),
            "total": len(items),
        },
        "warn_days": settings.urgency_warn_days,
    }
