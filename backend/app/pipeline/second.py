"""A second person for the risky purchase orders.

Four rules, each switched on in Settings (all are off until then, because the numbers are the company's to
choose): a large total, a supplier with no delivered order yet, a supplier whose bank account changed
lately, a linked contract with an open red remark. An order that meets any of them is not created by one
person's approval. The first approver asks; a different person confirms, and only that creates the order.
The rules read recorded facts and a person's settings; nothing here scores, ranks or blocks a quote."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.legal.service import request_summary
from app.models import PurchaseOrder, SecondApproval, Supplier, SupplierBankChange


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def assess(
    session: Session, settings: Settings, request_id: int, supplier: Supplier, total_eur: float
) -> list[dict]:
    """The rules this order meets, each with the fact behind it. Empty when none is switched on or met."""
    risks: list[dict] = []
    if settings.second_over_eur > 0 and total_eur > settings.second_over_eur:
        risks.append(
            {
                "kind": "large_sum",
                "text": f"the order total {total_eur:,.2f} EUR is above {settings.second_over_eur:,.2f} EUR",
            }
        )
    if settings.second_new_supplier:
        delivered = session.scalar(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(
                PurchaseOrder.supplier_id == supplier.id,
                PurchaseOrder.request_id != request_id,
                PurchaseOrder.delivery_status == "delivered",
            )
        )
        if not delivered:
            risks.append(
                {"kind": "new_supplier", "text": f"{supplier.name} has no delivered order with us yet"}
            )
    if settings.second_bank_days > 0:
        since = datetime.now(UTC) - timedelta(days=settings.second_bank_days)
        changes = session.scalars(
            select(SupplierBankChange).where(
                SupplierBankChange.supplier_id == supplier.id, SupplierBankChange.status == "approved"
            )
        )
        recent = [c for c in changes if c.decided_at and _aware(c.decided_at) >= since]
        if recent:
            last = max(_aware(c.decided_at) for c in recent)
            risks.append(
                {
                    "kind": "bank_changed",
                    "text": f"the bank account of {supplier.name} was changed on {last.date().isoformat()}"
                    f" (within {settings.second_bank_days} days)",
                }
            )
    if settings.second_legal_red:
        red = request_summary(session, request_id)["open_red"]
        if red:
            risks.append(
                {"kind": "legal_red", "text": f"{red} red remark(s) on a linked contract are still open"}
            )
    return risks


def ask(session: Session, request_id: int, by: str, risks: list[dict]) -> SecondApproval:
    """Record that `by` approved and a second person is needed. An ask already waiting is renewed."""
    row = session.scalar(
        select(SecondApproval).where(
            SecondApproval.request_id == request_id, SecondApproval.status == "pending"
        )
    )
    if row is None:
        row = SecondApproval(request_id=request_id, requested_by=by, risks=risks)
        session.add(row)
    else:
        row.requested_by, row.risks, row.requested_at = by, risks, datetime.now(UTC)
    session.commit()
    return row


def pending_for(session: Session, request_id: int) -> SecondApproval | None:
    return session.scalar(
        select(SecondApproval).where(
            SecondApproval.request_id == request_id, SecondApproval.status == "pending"
        )
    )


def view(row: SecondApproval) -> dict:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "risks": row.risks,
        "requested_by": row.requested_by,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "status": row.status,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "comment": row.comment,
    }


def listing(session: Session, status: str = "pending") -> list[dict]:
    if status not in ("pending", "confirmed", "rejected", "all"):
        raise ValueError("status must be pending, confirmed, rejected or all")
    q = select(SecondApproval).order_by(SecondApproval.id.desc())
    if status != "all":
        q = q.where(SecondApproval.status == status)
    return [view(r) for r in session.scalars(q)]
