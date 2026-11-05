"""The draft checklists and where a person stands on each line. The lines are fixed text with their sources
(items.py); only the state of a line is stored, with the person who set it and a note."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checklists.items import AREAS, CHECKED_ON, ITEMS, STATES
from app.models import AuditLog, ChecklistProgress
from app.pipeline.service import PipelineError

NOTE = (
    "DRAFT reading aid, not legal advice. Each line names its source and whether that is a primary or a "
    "secondary one; a date that is not from a primary source is marked. Check the source before use."
)


def _view(item: dict, row: ChecklistProgress | None) -> dict:
    return {
        **item,
        "date_marked": item["date"] is not None and item["date_basis"] != "primary",
        "progress": None
        if row is None
        else {"state": row.state, "note": row.note, "set_by": row.set_by, "set_at": row.set_at.isoformat()},
    }


def listing(session: Session) -> dict:
    rows = {r.key: r for r in session.scalars(select(ChecklistProgress))}
    areas = []
    for key, title in AREAS.items():
        items = [_view(i, rows.get(i["key"])) for i in ITEMS if i["area"] == key]
        done = sum(1 for i in items if i["progress"] and i["progress"]["state"] != "todo")
        areas.append({"key": key, "title": title, "items": items, "answered": done, "total": len(items)})
    return {"checked_on": CHECKED_ON, "note": NOTE, "areas": areas}


def set_state(session: Session, key: str, state: str, note: str, who: str) -> dict:
    item = next((i for i in ITEMS if i["key"] == key), None)
    if item is None:
        raise LookupError("no such checklist line")
    if state not in STATES:
        raise ValueError(f"state must be one of {', '.join(STATES)}")
    who = (who or "").strip()
    if not who:
        raise PipelineError("a named person is required for this action")
    note = (note or "").strip()
    if len(note) > 300:
        raise ValueError("the note is at most 300 characters")
    if state == "not_applicable" and len(note) < 3:
        raise ValueError("say why it does not apply to you")
    row = session.get(ChecklistProgress, key)
    before = row.state if row else None
    if row is None:
        row = ChecklistProgress(key=key, state=state, note=note, set_by=who, set_at=datetime.now(UTC))
        session.add(row)
    else:
        row.state, row.note, row.set_by = state, note, who
        row.set_at = datetime.now(UTC)
    session.add(
        AuditLog(
            actor="human",
            actor_id=who,
            action="checklist.set",
            payload={"key": key, "from": before, "to": state},
        )
    )
    session.commit()
    session.refresh(row)
    return _view(item, row)
