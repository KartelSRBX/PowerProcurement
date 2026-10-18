"""Access vault: logins for supplier portals, stored encrypted.

Seeing a login and password takes two people: one asks, a different one approves, and the approved
request can be used once within a short time. Every step is logged. Without sign-in the app only knows
the name a person typed, so this is a process aid, not a lock: see docs/decisions/0009-access-vault.md."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditLog, Supplier, VaultEntry, VaultLog, VaultRequest
from app.pipeline.service import PipelineError
from app.runtime import vault as crypto

APPROVAL_VALID_FOR = timedelta(minutes=15)
CATEGORIES = ("supplier portal", "distributor", "software", "customer portal", "other")


def _person(name: str) -> str:
    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _log(session: Session, event: str, person: str, entry_id: int | None = None, detail: str | None = None):
    session.add(VaultLog(event=event, person=person, entry_id=entry_id, detail=detail))


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def _entry_dict(e: VaultEntry) -> dict:
    return {
        "id": e.id,
        "category": e.category,
        "name": e.name,
        "site_url": e.site_url,
        "comments": e.comments,
        "supplier_id": e.supplier_id,
        "updated_by": e.updated_by,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _request_dict(r: VaultRequest, entry: VaultEntry | None = None) -> dict:
    approved_until = None
    if r.status == "approved" and r.decided_at:
        approved_until = (_aware(r.decided_at) + APPROVAL_VALID_FOR).isoformat()
    return {
        "id": r.id,
        "entry_id": r.entry_id,
        "entry_name": entry.name if entry else None,
        "requested_by": r.requested_by,
        "reason": r.reason,
        "status": r.status,
        "decided_by": r.decided_by,
        "decision_comment": r.decision_comment,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "approved_until": approved_until,
        "revealed_at": r.revealed_at.isoformat() if r.revealed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _entry(session: Session, entry_id: int) -> VaultEntry:
    e = session.get(VaultEntry, entry_id)
    if e is None:
        raise LookupError("vault entry not found")
    return e


def _clean(data: dict, settings: Settings, partial: bool) -> dict:
    out: dict = {}
    for key in ("category", "name", "site_url", "comments"):
        if key in data:
            out[key] = (data[key] or "").strip() or None
    if not partial or "name" in out:
        if not out.get("name"):
            raise ValueError("name is required")
    if "category" in out and (out["category"] is None or out["category"] not in CATEGORIES):
        raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
    if not partial and "category" not in out:
        raise ValueError("category is required")
    for key in ("login", "password"):
        if key in data and data[key] not in (None, ""):
            out[f"{key}_encrypted"] = crypto.encrypt(settings, data[key])
        elif not partial:
            raise ValueError(f"{key} is required")
    return out


def open_vault(session: Session, person: str) -> None:
    by = _person(person)
    _log(session, "opened", by)
    session.commit()


def list_entries(session: Session) -> list[dict]:
    return [
        _entry_dict(e)
        for e in session.scalars(select(VaultEntry).order_by(VaultEntry.category, VaultEntry.name))
    ]


def add_entry(session: Session, data: dict, changed_by: str, settings: Settings) -> dict:
    by = _person(changed_by)
    fields = _clean(data, settings, partial=False)
    sid = data.get("supplier_id")
    if sid is not None and session.get(Supplier, sid) is None:
        raise LookupError("supplier not found")
    row = VaultEntry(**fields, supplier_id=sid, updated_by=by)
    session.add(row)
    session.flush()
    _log(session, "created", by, row.id, row.name)
    session.add(AuditLog(actor="human", actor_id=by, action="vault.created", payload={"entry_id": row.id}))
    session.commit()
    session.refresh(row)
    return _entry_dict(row)


def update_entry(session: Session, entry_id: int, data: dict, changed_by: str, settings: Settings) -> dict:
    by = _person(changed_by)
    row = _entry(session, entry_id)
    fields = _clean(data, settings, partial=True)
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_by = by
    _log(session, "updated", by, row.id, ", ".join(sorted(k.replace("_encrypted", "") for k in fields)))
    session.add(AuditLog(actor="human", actor_id=by, action="vault.updated", payload={"entry_id": row.id}))
    session.commit()
    session.refresh(row)
    return _entry_dict(row)


def delete_entry(session: Session, entry_id: int, changed_by: str) -> None:
    by = _person(changed_by)
    row = _entry(session, entry_id)
    for r in session.scalars(select(VaultRequest).where(VaultRequest.entry_id == entry_id)):
        session.delete(r)
    _log(session, "deleted", by, entry_id, row.name)
    session.add(AuditLog(actor="human", actor_id=by, action="vault.deleted", payload={"entry_id": entry_id}))
    session.delete(row)
    session.commit()


def request_view(session: Session, entry_id: int, requested_by: str, reason: str) -> dict:
    by = _person(requested_by)
    entry = _entry(session, entry_id)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("say why you need to see it")
    open_one = session.scalar(
        select(VaultRequest).where(
            VaultRequest.entry_id == entry_id,
            VaultRequest.requested_by == by,
            VaultRequest.status.in_(("pending", "approved")),
            VaultRequest.revealed_at.is_(None),
        )
    )
    if open_one is not None and not _expired(open_one):
        raise PipelineError("you already have an open request for this entry")
    row = VaultRequest(entry_id=entry_id, requested_by=by, reason=reason)
    session.add(row)
    session.flush()
    _log(session, "requested", by, entry_id, reason)
    session.commit()
    session.refresh(row)
    return _request_dict(row, entry)


def _expired(r: VaultRequest) -> bool:
    return r.status == "approved" and _now() > _aware(r.decided_at) + APPROVAL_VALID_FOR


def list_requests(session: Session, status: str = "") -> list[dict]:
    q = select(VaultRequest).order_by(VaultRequest.id.desc()).limit(200)
    if status:
        q = q.where(VaultRequest.status == status)
    names = {e.id: e for e in session.scalars(select(VaultEntry))}
    out = []
    for r in session.scalars(q):
        d = _request_dict(r, names.get(r.entry_id))
        if _expired(r):
            d["status"] = "expired"
        out.append(d)
    return out


def decide(session: Session, request_id: int, decided_by: str, approve: bool, comment: str = "") -> dict:
    by = _person(decided_by)
    r = session.get(VaultRequest, request_id)
    if r is None:
        raise LookupError("request not found")
    if r.status != "pending":
        raise PipelineError(f"request is already {r.status}")
    if by.casefold() == r.requested_by.casefold():
        raise PipelineError("a different person has to decide this request")
    r.status = "approved" if approve else "rejected"
    r.decided_by, r.decided_at = by, _now()
    r.decision_comment = (comment or "").strip() or None
    _log(
        session, "approved" if approve else "rejected", by, r.entry_id, f"request {r.id} by {r.requested_by}"
    )
    session.commit()
    return _request_dict(r, session.get(VaultEntry, r.entry_id))


def reveal(session: Session, request_id: int, person: str, settings: Settings) -> dict:
    by = _person(person)
    r = session.get(VaultRequest, request_id)
    if r is None:
        raise LookupError("request not found")
    if by.casefold() != r.requested_by.casefold():
        raise PipelineError("only the person who asked can open this")
    if r.status != "approved":
        raise PipelineError(f"request is {r.status}, not approved")
    if r.revealed_at is not None:
        raise PipelineError("this approval was already used; ask again")
    if _expired(r):
        raise PipelineError("the approval expired; ask again")
    entry = _entry(session, r.entry_id)
    login = crypto.decrypt(settings, entry.login_encrypted)
    password = crypto.decrypt(settings, entry.password_encrypted)
    if login is None or password is None:
        raise PipelineError("this entry cannot be decrypted with the current key (was the key replaced?)")
    r.revealed_at = _now()
    r.status = "used"
    _log(session, "revealed", by, entry.id, f"request {r.id}, approved by {r.decided_by}")
    session.commit()
    return {"entry": _entry_dict(entry), "login": login, "password": password}


def log_rows(session: Session, limit: int = 100) -> list[dict]:
    rows = session.scalars(select(VaultLog).order_by(VaultLog.id.desc()).limit(max(1, min(limit, 500))))
    return [
        {
            "id": r.id,
            "event": r.event,
            "person": r.person,
            "entry_id": r.entry_id,
            "detail": r.detail,
            "at": r.at.isoformat() if r.at else None,
        }
        for r in rows
    ]
