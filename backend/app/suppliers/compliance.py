"""Supplier re-checks. Two things a buyer is expected to keep current; the app only keeps the record:

- Sanctions screening. No list is downloaded and nothing is matched here. A person checks the supplier
  against a list they name, and records the date, the list and what they found (clear, a match, or unclear).
- The beneficiary: who owns the company in the end, as a person recorded it, with where that was learned.

Both go stale. A screening counts for a number of months (a default in Settings, a period set for one
supplier, or a date a person chose); the list shows what is overdue, never done, or coming due. A match or
an unclear result is shown as needing attention until a later screening says otherwise. Nothing here
changes a score or blocks a supplier: marking one sanctioned stays a separate, deliberate step."""

import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    AuditLog,
    PurchaseOrder,
    Supplier,
    SupplierCompliance,
    SupplierScreening,
)
from app.pipeline.service import PipelineError

RESULTS = {"clear": "nothing found", "match": "a possible match was found", "unclear": "could not be decided"}
SOURCES = {
    "business_register": "an extract from the business register",
    "supplier_declaration": "a declaration from the supplier",
    "other": "another source (explain)",
}
MAX_OWNERS = 20


def _person(name: str) -> str:
    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _audit(session: Session, person: str, action: str, **payload) -> None:
    session.add(AuditLog(actor="human", actor_id=person, action=action, payload=payload))


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _row(session: Session, supplier_id: int) -> SupplierCompliance | None:
    return session.scalar(select(SupplierCompliance).where(SupplierCompliance.supplier_id == supplier_id))


def _ensure(session: Session, supplier_id: int) -> SupplierCompliance:
    if session.get(Supplier, supplier_id) is None:
        raise LookupError("supplier not found")
    row = _row(session, supplier_id)
    if row is None:
        row = SupplierCompliance(supplier_id=supplier_id, beneficial_owners=[])
        session.add(row)
        session.flush()
    return row


def _screening_dict(r: SupplierScreening) -> dict:
    return {
        "id": r.id,
        "checked_on": r.checked_on.isoformat(),
        "list_name": r.list_name,
        "result": r.result,
        "result_label": RESULTS.get(r.result, r.result),
        "note": r.note,
        "checked_by": r.checked_by,
    }


def _standing(
    last: SupplierScreening | None, comp: SupplierCompliance | None, settings: Settings, today: date
) -> dict:
    """Where a supplier's screening stands: never, ok, due_soon or overdue, and the date it falls due."""
    months = (comp.period_months if comp and comp.period_months else None) or settings.recheck_months
    due, basis = None, None
    if comp is not None and comp.next_check_on is not None:
        due, basis = comp.next_check_on, "a date set by a person"
    elif last is not None:
        due, basis = add_months(last.checked_on, months), f"{months} month(s) after the last screening"
    if due is None:
        status, days = "never", None
    else:
        days = (due - today).days
        status = "overdue" if days < 0 else "due_soon" if days <= settings.recheck_warn_days else "ok"
    return {
        "status": status,
        "due_on": due.isoformat() if due else None,
        "days_left": days,
        "basis": basis,
        "period_months": months,
        "own_period": bool(comp and comp.period_months),
        "attention": last is not None and last.result in ("match", "unclear"),
    }


def _beneficiary(comp: SupplierCompliance | None, settings: Settings, today: date) -> dict:
    if comp is None or comp.beneficial_on is None:
        return {"recorded": False, "status": "never", "owners": []}
    months = comp.period_months or settings.recheck_months
    due = add_months(comp.beneficial_on, months)
    days = (due - today).days
    return {
        "recorded": True,
        "owners": comp.beneficial_owners,
        "source": comp.beneficial_source,
        "source_label": SOURCES.get(comp.beneficial_source or "", comp.beneficial_source),
        "note": comp.beneficial_note,
        "confirmed_on": comp.beneficial_on.isoformat(),
        "confirmed_by": comp.beneficial_by,
        "due_on": due.isoformat(),
        "days_left": days,
        "status": "overdue" if days < 0 else "due_soon" if days <= settings.recheck_warn_days else "ok",
    }


def view(session: Session, settings: Settings, supplier_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    if session.get(Supplier, supplier_id) is None:
        raise LookupError("supplier not found")
    screenings = list(
        session.scalars(
            select(SupplierScreening)
            .where(SupplierScreening.supplier_id == supplier_id)
            .order_by(SupplierScreening.checked_on.desc(), SupplierScreening.id.desc())
        )
    )
    comp = _row(session, supplier_id)
    return {
        "supplier_id": supplier_id,
        "screening": _standing(screenings[0] if screenings else None, comp, settings, today),
        "last": _screening_dict(screenings[0]) if screenings else None,
        "history": [_screening_dict(r) for r in screenings[:10]],
        "next_check_on": comp.next_check_on.isoformat() if comp and comp.next_check_on else None,
        "beneficiary": _beneficiary(comp, settings, today),
        "results": RESULTS,
        "sources": SOURCES,
        "default_months": settings.recheck_months,
        "list_names": sorted({r.list_name for r in session.scalars(select(SupplierScreening))}),
    }


def record_screening(
    session: Session,
    supplier_id: int,
    checked_by: str,
    checked_on: date,
    list_name: str,
    result: str,
    note: str = "",
) -> dict:
    who = _person(checked_by)
    comp = _ensure(session, supplier_id)
    list_name, note = list_name.strip(), note.strip()
    if not list_name:
        raise ValueError("name the list that was checked")
    if result not in RESULTS:
        raise ValueError(f"the result must be one of: {', '.join(RESULTS)}")
    if checked_on > date.today():
        raise ValueError("a screening cannot be dated in the future")
    if result != "clear" and len(note) < 3:
        raise ValueError("say what was found: a note is required unless nothing was found")
    row = SupplierScreening(
        supplier_id=supplier_id,
        checked_on=checked_on,
        list_name=list_name[:160],
        result=result,
        note=note[:300],
        checked_by=who,
    )
    session.add(row)
    session.flush()
    cleared = None
    if comp.next_check_on is not None and comp.next_check_on <= checked_on:
        cleared, comp.next_check_on = comp.next_check_on.isoformat(), None
    _audit(
        session,
        who,
        "supplier.screened",
        supplier_id=supplier_id,
        list=row.list_name,
        result=result,
        on=checked_on.isoformat(),
        cleared_date=cleared,
    )
    session.commit()
    return _screening_dict(row)


def remove_screening(session: Session, screening_id: int, removed_by: str) -> int:
    who = _person(removed_by)
    row = session.get(SupplierScreening, screening_id)
    if row is None:
        raise LookupError("screening not found")
    supplier_id = row.supplier_id
    _audit(
        session,
        who,
        "supplier.screening_removed",
        supplier_id=supplier_id,
        list=row.list_name,
        result=row.result,
        on=row.checked_on.isoformat(),
    )
    session.delete(row)
    session.commit()
    return supplier_id


def set_schedule(
    session: Session,
    supplier_id: int,
    changed_by: str,
    period_months: int | None,
    next_check_on: date | None,
) -> dict:
    who = _person(changed_by)
    if period_months is not None and not 1 <= period_months <= 60:
        raise ValueError("the period is 1 to 60 months")
    comp = _ensure(session, supplier_id)
    before = {"period_months": comp.period_months, "next_check_on": str(comp.next_check_on)}
    comp.period_months, comp.next_check_on = period_months, next_check_on
    _audit(
        session,
        who,
        "supplier.recheck_schedule",
        supplier_id=supplier_id,
        before=before,
        after={"period_months": period_months, "next_check_on": str(next_check_on)},
    )
    session.commit()
    return {"period_months": period_months, "next_check_on": next_check_on}


def set_beneficiary(
    session: Session,
    supplier_id: int,
    confirmed_by: str,
    owners: list[str],
    source: str,
    confirmed_on: date,
    note: str = "",
) -> None:
    who = _person(confirmed_by)
    comp = _ensure(session, supplier_id)
    names, seen = [], set()
    for raw in owners:
        name = " ".join(raw.split())
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name[:200])
    if len(names) > MAX_OWNERS:
        raise ValueError(f"at most {MAX_OWNERS} names")
    if source not in SOURCES:
        raise ValueError(f"the source must be one of: {', '.join(SOURCES)}")
    note = note.strip()
    if (not names or source == "other") and len(note) < 3:
        raise ValueError(
            "explain: a note is required when no owner is named or the source is 'other'"
            if not names
            else "explain the source in the note"
        )
    if confirmed_on > date.today():
        raise ValueError("the confirmation cannot be dated in the future")
    before = list(comp.beneficial_owners or [])
    comp.beneficial_owners, comp.beneficial_source = names, source
    comp.beneficial_note, comp.beneficial_on, comp.beneficial_by = note[:300] or None, confirmed_on, who
    _audit(
        session,
        who,
        "supplier.beneficiary_recorded",
        supplier_id=supplier_id,
        before=before,
        after=names,
        source=source,
    )
    session.commit()


def rechecks(session: Session, settings: Settings, today: date | None = None) -> dict:
    """Suppliers whose screening or beneficiary needs a person: overdue, never done, coming due, or a
    result that still needs attention. Suppliers put on hold are left out."""
    today = today or date.today()
    last: dict[int, SupplierScreening] = {}
    for r in session.scalars(
        select(SupplierScreening).order_by(SupplierScreening.checked_on, SupplierScreening.id)
    ):
        last[r.supplier_id] = r
    comps = {c.supplier_id: c for c in session.scalars(select(SupplierCompliance))}
    ordered = {po.supplier_id for po in session.scalars(select(PurchaseOrder))}
    items = []
    for s in session.scalars(select(Supplier).order_by(Supplier.name)):
        if s.partner_status == "on_hold":
            continue
        scr = _standing(last.get(s.id), comps.get(s.id), settings, today)
        ben = _beneficiary(comps.get(s.id), settings, today)
        reasons = []
        if scr["attention"]:
            reasons.append(f"last screening: {RESULTS[last[s.id].result]}")
        if scr["status"] == "never":
            reasons.append("never screened")
        elif scr["status"] == "overdue":
            reasons.append(f"screening overdue by {-scr['days_left']} day(s)")
        elif scr["status"] == "due_soon":
            reasons.append(f"screening due in {scr['days_left']} day(s)")
        if ben["status"] == "never":
            reasons.append("beneficiary not recorded")
        elif ben["status"] == "overdue":
            reasons.append(f"beneficiary confirmation overdue by {-ben['days_left']} day(s)")
        elif ben["status"] == "due_soon":
            reasons.append(f"beneficiary confirmation due in {ben['days_left']} day(s)")
        if not reasons:
            continue
        rank = (
            0
            if scr["attention"]
            else 1
            if scr["status"] == "overdue"
            else 2
            if scr["status"] == "never"
            else 3
        )
        items.append(
            {
                "supplier_id": s.id,
                "name": s.name,
                "country": s.country,
                "has_orders": s.id in ordered,
                "screening": scr,
                "beneficiary": ben,
                "reasons": reasons,
                "_sort": (
                    rank,
                    s.id not in ordered,
                    scr["days_left"] if scr["days_left"] is not None else 0,
                    s.name,
                ),
            }
        )
    items.sort(key=lambda i: i["_sort"])
    for i in items:
        del i["_sort"]
    return {
        "items": items,
        "counts": {
            "attention": sum(1 for i in items if i["screening"]["attention"]),
            "overdue": sum(1 for i in items if i["screening"]["status"] == "overdue"),
            "never": sum(1 for i in items if i["screening"]["status"] == "never"),
            "due_soon": sum(1 for i in items if i["screening"]["status"] == "due_soon"),
            "no_beneficiary": sum(1 for i in items if i["beneficiary"]["status"] == "never"),
        },
        "default_months": settings.recheck_months,
        "warn_days": settings.recheck_warn_days,
    }
