"""The delivery record of a purchase order: the date the supplier is expected to deliver, where the goods
are, and a history of every change with who made it and why. A date the offer's lead time gave is a
calculation, not a promise: the status stays "ordered" until a person records that the supplier confirmed.
Code decides what is overdue; a person records what the supplier says."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeliveryEvent, Letter, PurchaseOrder, Supplier
from app.pipeline.service import PipelineError, _audit, _need_person

STATUSES = ("ordered", "confirmed", "shipped", "delivered", "cancelled")
FINAL = ("delivered", "cancelled")
LABELS = {
    "ordered": "ordered, no confirmation yet",
    "confirmed": "supplier confirmed the date",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
}


def _order(session: Session, po_id: int) -> PurchaseOrder:
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        raise LookupError("purchase order not found")
    return po


def overdue_days(po: PurchaseOrder, today: date) -> int:
    if po.delivery_status in FINAL or po.promised_date is None or po.promised_date >= today:
        return 0
    return (today - po.promised_date).days


def view(session: Session, po_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    po = _order(session, po_id)
    history = session.scalars(
        select(DeliveryEvent).where(DeliveryEvent.order_id == po.id).order_by(DeliveryEvent.id)
    )
    return {
        "order_id": po.id,
        "request_id": po.request_id,
        "ordered_on": po.created_at.date().isoformat() if po.created_at else None,
        "promised_date": po.promised_date.isoformat() if po.promised_date else None,
        "status": po.delivery_status,
        "status_label": LABELS[po.delivery_status],
        "delivered_date": po.delivered_date.isoformat() if po.delivered_date else None,
        "overdue_days": overdue_days(po, today),
        "final": po.delivery_status in FINAL,
        "history": [
            {
                "id": e.id,
                "at": e.created_at.isoformat() if e.created_at else None,
                "kind": e.kind,
                "old": e.old_value,
                "new": e.new_value,
                "reason": e.reason,
                "by": e.changed_by,
            }
            for e in history
        ],
    }


def update(
    session: Session,
    po_id: int,
    changed_by: str,
    promised_date: date | None = None,
    status: str | None = None,
    delivered_date: date | None = None,
    reason: str = "",
    today: date | None = None,
) -> dict:
    """Change the promised date and/or the status. Moving a date that was already set needs a reason, so the
    history says why it moved. Delivered and cancelled are final."""
    by = _need_person(changed_by)
    today = today or date.today()
    po = _order(session, po_id)
    reason = reason.strip()
    if po.delivery_status in FINAL:
        raise PipelineError(f"the order is {po.delivery_status}: its delivery record is closed")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    if promised_date is None and status is None and delivered_date is None:
        raise ValueError("nothing to change")
    ordered_on = po.created_at.date() if po.created_at else today

    if promised_date is not None and promised_date != po.promised_date:
        if promised_date < ordered_on:
            raise PipelineError(f"the promised date cannot be before the order date {ordered_on.isoformat()}")
        if po.promised_date is not None and not reason:
            raise PipelineError("say why the date moved: a reason is required to change a date")
        session.add(
            DeliveryEvent(
                order_id=po.id,
                kind="promised_date",
                old_value=po.promised_date.isoformat() if po.promised_date else None,
                new_value=promised_date.isoformat(),
                reason=reason or "first date given",
                changed_by=by,
            )
        )
        po.promised_date = promised_date

    if status is not None and status != po.delivery_status:
        if status == "delivered":
            delivered_date = delivered_date or today
            if delivered_date > today:
                raise PipelineError("a delivery date cannot be in the future")
            if delivered_date < ordered_on:
                raise PipelineError(
                    f"the delivery date cannot be before the order date {ordered_on.isoformat()}"
                )
            po.delivered_date = delivered_date
            session.add(
                DeliveryEvent(
                    order_id=po.id,
                    kind="delivered_date",
                    old_value=None,
                    new_value=delivered_date.isoformat(),
                    reason=reason,
                    changed_by=by,
                )
            )
        elif delivered_date is not None:
            raise PipelineError("a delivery date can only be given together with the status delivered")
        session.add(
            DeliveryEvent(
                order_id=po.id,
                kind="status",
                old_value=po.delivery_status,
                new_value=status,
                reason=reason,
                changed_by=by,
            )
        )
        po.delivery_status = status
    elif delivered_date is not None:
        raise PipelineError("a delivery date can only be given together with the status delivered")

    _audit(
        session,
        "human",
        by,
        "po.delivery_updated",
        order_id=po.id,
        promised_date=po.promised_date.isoformat() if po.promised_date else None,
        status=po.delivery_status,
        reason=reason,
    )
    session.commit()
    return view(session, po_id, today)


def overdue_orders(session: Session, today: date | None = None) -> list[dict]:
    """Every open order whose promised date has passed, the most late first, with the state of the question to
    its supplier (none, waiting for approval, or sent and when)."""
    today = today or date.today()
    rows = []
    for po in session.scalars(select(PurchaseOrder).where(PurchaseOrder.promised_date.is_not(None))):
        days = overdue_days(po, today)
        if days == 0:
            continue
        sup = session.get(Supplier, po.supplier_id)
        letters = list(
            session.scalars(
                select(Letter).where(Letter.order_id == po.id, Letter.kind == "delay").order_by(Letter.id)
            )
        )
        waiting = next((x for x in letters if x.status == "draft"), None)
        sent = [x for x in letters if x.status == "sent"]
        last = sent[-1].created_at if sent else None
        rows.append(
            {
                "order_id": po.id,
                "request_id": po.request_id,
                "supplier_id": sup.id,
                "supplier": sup.name,
                "promised_date": po.promised_date.isoformat(),
                "status": po.delivery_status,
                "status_label": LABELS[po.delivery_status],
                "overdue_days": days,
                "question": "waiting" if waiting else "sent" if sent else "none",
                "question_letter_id": waiting.id if waiting else None,
                "last_asked": last.date().isoformat() if last else None,
            }
        )
    return sorted(rows, key=lambda r: (-r["overdue_days"], r["order_id"]))
