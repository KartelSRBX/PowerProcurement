"""The supplier's invoice for an order, compared with what was ordered. A person types the invoice in
(nothing is read from a file or a mail here); code compares it with the offer behind the order, and a
person accepts it.

What is compared, all without VAT: the invoice total against the offer's total, and, when the invoice has
lines, each requested item's quantity (exact) and unit price (within the tolerance set in Settings). Where the
invoice and the offer use different currencies both are converted to EUR at the rate in Settings. Nothing is
paid or posted anywhere: accepting only records that a named person looked at the comparison."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import to_eur
from app.models import Offer, OfferLine, PurchaseOrder, Supplier, SupplierInvoice
from app.pipeline.service import PipelineError, _audit, _need_person, items_of

ROUNDING = 0.05  # money in the invoice's own currency: a cent or so of rounding is not a difference


def _order(session: Session, po_id: int) -> PurchaseOrder:
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        raise LookupError("purchase order not found")
    return po


def _get(session: Session, po_id: int) -> SupplierInvoice | None:
    return session.scalar(select(SupplierInvoice).where(SupplierInvoice.order_id == po_id))


def _eur(amount: float, currency: str, settings: Settings) -> float:
    return to_eur(amount, currency, settings)


def _norm(number: str) -> str:
    """Letters and digits only, case ignored: INV-2026/0417 and inv 2026 0417 are the same number."""
    return "".join(ch for ch in number.casefold() if ch.isalnum())


def duplicates(session: Session, po: PurchaseOrder, inv: SupplierInvoice) -> list[SupplierInvoice]:
    """Other invoices from the same supplier with the same number: entered twice, or paid twice."""
    mine = _norm(inv.number)
    if not mine:
        return []
    rows = session.scalars(
        select(SupplierInvoice)
        .join(PurchaseOrder, PurchaseOrder.id == SupplierInvoice.order_id)
        .where(PurchaseOrder.supplier_id == po.supplier_id, SupplierInvoice.id != inv.id)
        .order_by(SupplierInvoice.id)
    )
    return [o for o in rows if _norm(o.number) == mine]


def compare(session: Session, settings: Settings, po: PurchaseOrder, inv: SupplierInvoice) -> dict:
    """The invoice against the order. Computed on every read, so a changed tolerance applies at once."""
    tol = settings.invoice_tolerance_pct
    offer = session.get(Offer, po.offer_id)
    issues: list[dict] = []
    notes: list[str] = []

    def issue(kind: str, text: str, item_id: int | None = None) -> None:
        issues.append({"kind": kind, "text": text, "item_id": item_id})

    same = inv.currency == offer.currency
    if same:
        ordered, invoiced, unit = offer.total_price, inv.total_net, offer.currency
    else:
        ordered = _eur(offer.total_price, offer.currency, settings)
        invoiced = _eur(inv.total_net, inv.currency, settings)
        unit = "EUR"
        notes.append(
            f"the invoice is in {inv.currency} and the offer in {offer.currency}: "
            "compared in EUR at the rate in Settings"
        )
    diff = invoiced - ordered
    pct = round(100 * diff / ordered, 2) if ordered else None
    total_ok = ordered > 0 and abs(diff) <= tol / 100 * ordered + 1e-9
    if not total_ok:
        way = "more" if diff > 0 else "less"
        issue(
            "total",
            f"the invoice total is {abs(round(diff, 2)):,.2f} {unit} {way} than the order "
            f"({pct:+.2f}%, tolerance {tol:g}%)",
        )

    items = items_of(session, po.request_id)
    prices = {
        ol.item_id: ol.unit_price
        for ol in session.scalars(select(OfferLine).where(OfferLine.offer_id == po.offer_id))
    }
    got = {ln["item_id"]: ln for ln in (inv.lines or [])}
    lines = []
    if inv.lines:
        for it in items:
            ln = got.get(it.id)
            want_price = prices.get(it.id)
            row = {
                "item_id": it.id,
                "description": it.description,
                "ordered_quantity": it.quantity,
                "ordered_unit_price": want_price,
                "invoiced_quantity": ln["quantity"] if ln else None,
                "invoiced_unit_price": ln["unit_price"] if ln else None,
                "quantity_ok": None,
                "price_pct": None,
                "price_ok": None,
            }
            if ln is None:
                row["quantity_ok"] = False
                issue("missing_item", f"“{it.description}” is not on the invoice", it.id)
            else:
                if it.quantity is not None:
                    row["quantity_ok"] = abs(ln["quantity"] - it.quantity) < 1e-9
                    if not row["quantity_ok"]:
                        issue(
                            "quantity",
                            f"“{it.description}”: {ln['quantity']:g} invoiced, {it.quantity:g} ordered",
                            it.id,
                        )
                if want_price:
                    price = ln["unit_price"]
                    if not same:
                        price, want = (
                            _eur(price, inv.currency, settings),
                            _eur(want_price, offer.currency, settings),
                        )
                    else:
                        want = want_price
                    row["price_pct"] = round(100 * (price - want) / want, 2)
                    row["price_ok"] = abs(price - want) <= tol / 100 * want + 1e-9
                    if not row["price_ok"]:
                        issue(
                            "price",
                            f"“{it.description}”: unit price {ln['unit_price']:g} {inv.currency} against "
                            f"{want_price:g} {offer.currency} ordered ({row['price_pct']:+.2f}%)",
                            it.id,
                        )
            lines.append(row)
        sum_lines = sum(ln["quantity"] * ln["unit_price"] for ln in inv.lines)
        if abs(sum_lines - inv.total_net) > ROUNDING:
            issue(
                "lines_sum",
                f"the lines add up to {sum_lines:,.2f} {inv.currency}, the invoice total is "
                f"{inv.total_net:,.2f}: freight or other charges, or a typing error",
            )
        extra = [i for i in got if i not in {it.id for it in items}]
        if extra:
            issue("foreign_line", "the invoice has a line that is not an item of this order")
    for other in duplicates(session, po, inv):
        issue(
            "duplicate_number",
            f"the number {inv.number} is also on the invoice for order #{other.order_id} "
            f"({other.number}) from the same supplier",
        )
    return {
        "status": "matches" if not issues else "differs",
        "reasons": [i["text"] for i in issues],
        "issues": issues,
        "notes": notes,
        "tolerance_pct": tol,
        "compared_in": unit,
        "ordered_total": round(ordered, 2),
        "invoiced_total": round(invoiced, 2),
        "difference": round(diff, 2),
        "difference_pct": pct,
        "lines": lines,
        "ordered_in": offer.currency,
    }


def view(session: Session, settings: Settings, po_id: int) -> dict:
    po = _order(session, po_id)
    inv = _get(session, po_id)
    if inv is None:
        return {"order_id": po.id, "invoice": None, "comparison": None}
    return {
        "order_id": po.id,
        "invoice": {
            "id": inv.id,
            "number": inv.number,
            "invoice_date": inv.invoice_date.isoformat(),
            "currency": inv.currency,
            "total_net": inv.total_net,
            "vat_amount": inv.vat_amount,
            "lines": inv.lines,
            "note": inv.note,
            "entered_by": inv.entered_by,
            "entered_at": inv.entered_at.isoformat() if inv.entered_at else None,
            "accepted_by": inv.accepted_by,
            "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
            "accept_reason": inv.accept_reason,
        },
        "comparison": compare(session, settings, po, inv),
    }


def save(
    session: Session,
    settings: Settings,
    po_id: int,
    entered_by: str,
    number: str,
    invoice_date: date,
    currency: str,
    total_net: float,
    vat_amount: float | None = None,
    lines: list[dict] | None = None,
    note: str = "",
) -> dict:
    """Enter the invoice for an order, or replace it while nobody has accepted it."""
    by = _need_person(entered_by)
    po = _order(session, po_id)
    number, currency = number.strip(), currency.strip().upper()
    if not number:
        raise ValueError("the invoice number is required")
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a 3-letter code")
    if total_net <= 0:
        raise ValueError("the invoice total must be above zero")
    if vat_amount is not None and vat_amount < 0:
        raise ValueError("VAT cannot be negative")
    if invoice_date > date.today():
        raise PipelineError("an invoice cannot be dated in the future")
    if po.delivery_status == "cancelled":
        raise PipelineError(
            "the order is cancelled: an invoice for it has to be sorted out with the supplier first"
        )
    known = {i.id for i in items_of(session, po.request_id)}
    clean = None
    if lines:
        clean = []
        for ln in lines:
            if ln["item_id"] not in known:
                raise ValueError(f"item {ln['item_id']} is not an item of this order")
            if ln["quantity"] <= 0 or ln["unit_price"] < 0:
                raise ValueError("a line needs a quantity above zero and a price of zero or more")
            clean.append(
                {"item_id": ln["item_id"], "quantity": ln["quantity"], "unit_price": ln["unit_price"]}
            )
        if len({c["item_id"] for c in clean}) != len(clean):
            raise ValueError("an item appears twice on the invoice")
    inv = _get(session, po_id)
    if inv is not None and inv.accepted_by:
        raise PipelineError("this invoice has been accepted and can no longer be changed")
    fresh = inv is None
    if fresh:
        inv = SupplierInvoice(order_id=po.id, entered_by=by)
        session.add(inv)
    inv.number, inv.invoice_date, inv.currency = number, invoice_date, currency
    inv.total_net, inv.vat_amount, inv.lines, inv.note, inv.entered_by = (
        total_net,
        vat_amount,
        clean,
        note.strip()[:300],
        by,
    )
    _audit(
        session,
        "human",
        by,
        "invoice.entered" if fresh else "invoice.replaced",
        order_id=po.id,
        number=number,
    )
    session.commit()
    return view(session, settings, po_id)


def remove(session: Session, settings: Settings, po_id: int, removed_by: str) -> dict:
    by = _need_person(removed_by)
    _order(session, po_id)
    inv = _get(session, po_id)
    if inv is None:
        raise LookupError("there is no invoice on this order")
    if inv.accepted_by:
        raise PipelineError("this invoice has been accepted and can no longer be removed")
    _audit(session, "human", by, "invoice.removed", order_id=po_id, number=inv.number)
    session.delete(inv)
    session.commit()
    return view(session, settings, po_id)


def accept(session: Session, settings: Settings, po_id: int, accepted_by: str, reason: str = "") -> dict:
    """A named person accepts the invoice. Where it differs from the order, saying why is required."""
    by = _need_person(accepted_by)
    po = _order(session, po_id)
    inv = _get(session, po_id)
    if inv is None:
        raise LookupError("there is no invoice on this order")
    if inv.accepted_by:
        raise PipelineError(f"already accepted by {inv.accepted_by}")
    result = compare(session, settings, po, inv)
    reason = reason.strip()
    if result["status"] == "differs" and len(reason) < 3:
        raise PipelineError("the invoice differs from the order: say why it is accepted anyway")
    inv.accepted_by, inv.accepted_at, inv.accept_reason = by, datetime.now(UTC), reason or None
    _audit(
        session,
        "human",
        by,
        "invoice.accepted",
        order_id=po.id,
        number=inv.number,
        status=result["status"],
        reasons=result["reasons"],
        reason=reason,
    )
    session.commit()
    return view(session, settings, po_id)


KINDS = ("total", "price", "quantity", "missing_item", "lines_sum", "foreign_line", "duplicate_number")


def mismatches(session: Session, settings: Settings, kind: str | None = None, show: str = "open") -> dict:
    """Every invoice that differs from its order, with what differs, largest amount first. `show` is open
    (not yet accepted, the default), accepted (accepted although they differed) or all."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if show not in ("open", "accepted", "all"):
        raise ValueError("show must be open, accepted or all")
    rows, counts = [], dict.fromkeys(KINDS, 0)
    invs = session.scalars(select(SupplierInvoice).order_by(SupplierInvoice.id))
    for inv in invs:
        if (show == "open" and inv.accepted_by) or (show == "accepted" and not inv.accepted_by):
            continue
        po = session.get(PurchaseOrder, inv.order_id)
        cmp = compare(session, settings, po, inv)
        if not cmp["issues"]:
            continue
        kinds = sorted({i["kind"] for i in cmp["issues"]}, key=KINDS.index)
        for k in kinds:
            counts[k] += 1
        if kind is not None and kind not in kinds:
            continue
        sup = session.get(Supplier, po.supplier_id)
        offer = session.get(Offer, po.offer_id)
        eur_diff = _eur(inv.total_net, inv.currency, settings) - _eur(
            offer.total_price, offer.currency, settings
        )
        rows.append(
            {
                "order_id": po.id,
                "request_id": po.request_id,
                "supplier": sup.name,
                "number": inv.number,
                "invoice_date": inv.invoice_date.isoformat(),
                "currency": inv.currency,
                "total_net": inv.total_net,
                "difference": cmp["difference"],
                "difference_in": cmp["compared_in"],
                "difference_eur": round(eur_diff, 2),
                "kinds": kinds,
                "issues": cmp["issues"],
                "accepted_by": inv.accepted_by,
                "accept_reason": inv.accept_reason,
            }
        )
    rows.sort(key=lambda r: (-abs(r["difference_eur"]), r["order_id"]))
    return {"show": show, "kind": kind, "count": len(rows), "by_kind": counts, "rows": rows}
