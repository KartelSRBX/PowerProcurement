"""How a supplier has actually delivered, worked out from the delivery records of its orders. No new tables:
the promised dates, the history of their changes and the delivery dates are already on the orders. Plain
arithmetic, the same orders always give the same numbers; the page says how many orders a figure rests on.

"On time" is measured two ways, because they answer different questions: against the date in force when the
goods arrived (did they keep the date they last gave) and against the first date (did they keep the lead time
they quoted; the first date is calculated from it). "In full" is not measured: the delivery record holds no
received quantity."""

from datetime import date
from statistics import mean, median, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeliveryEvent, Offer, PurchaseOrder

MIN_ORDERS = 3  # fewer delivered orders than this say too little about a supplier
RECENT = 10


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _spread(values: list[int]) -> dict | None:
    if not values:
        return None
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(mean(values), 1),
        "median": median(values),
        "stdev": round(pstdev(values), 1),  # of these orders, not an estimate for all future ones
    }


def performance(
    session: Session, supplier_id: int, today: date | None = None, min_orders: int = MIN_ORDERS
) -> dict:
    today = today or date.today()
    pos = list(
        session.scalars(
            select(PurchaseOrder).where(PurchaseOrder.supplier_id == supplier_id).order_by(PurchaseOrder.id)
        )
    )
    events: dict[int, list[DeliveryEvent]] = {p.id: [] for p in pos}
    if pos:
        for e in session.scalars(
            select(DeliveryEvent)
            .where(DeliveryEvent.order_id.in_(list(events)), DeliveryEvent.kind == "promised_date")
            .order_by(DeliveryEvent.id)
        ):
            events[e.order_id].append(e)
    offers = {
        o.id: o for o in session.scalars(select(Offer).where(Offer.id.in_([p.offer_id for p in pos] or [0])))
    }

    delivered = [p for p in pos if p.delivery_status == "delivered" and p.delivered_date]
    rows, on_final, on_first, with_date = [], 0, 0, 0
    late_by, actual, quoted = [], [], []
    moves = moved_orders = 0
    for p in delivered:
        ordered = p.created_at.date() if p.created_at else p.delivered_date
        days = (p.delivered_date - ordered).days
        offer = offers.get(p.offer_id)
        evs = events[p.id]
        first = date.fromisoformat(evs[0].new_value) if evs else None
        later = sum(1 for e in evs if e.old_value and e.new_value > e.old_value)
        moves += later
        moved_orders += 1 if later else 0
        actual.append(days)
        if offer is not None:
            quoted.append(offer.lead_time_days)
        vs_final = (p.delivered_date - p.promised_date).days if p.promised_date else None
        vs_first = (p.delivered_date - first).days if first else None
        if vs_final is not None:
            with_date += 1
            on_final += 1 if vs_final <= 0 else 0
            if vs_final > 0:
                late_by.append(vs_final)
        on_first += 1 if vs_first is not None and vs_first <= 0 else 0
        rows.append(
            {
                "order_id": p.id,
                "request_id": p.request_id,
                "ordered_on": ordered.isoformat(),
                "quoted_days": offer.lead_time_days if offer else None,
                "actual_days": days,
                "first_date": first.isoformat() if first else None,
                "promised_date": p.promised_date.isoformat() if p.promised_date else None,
                "delivered_date": p.delivered_date.isoformat(),
                "days_vs_promise": vs_final,
                "days_vs_first": vs_first,
                "date_moves": later,
            }
        )
    n = len(delivered)
    first_known = sum(1 for r in rows if r["days_vs_first"] is not None)
    enough = n >= min_orders
    return {
        "supplier_id": supplier_id,
        "orders": {
            "total": len(pos),
            "delivered": n,
            "open": sum(1 for p in pos if p.delivery_status not in ("delivered", "cancelled")),
            "cancelled": sum(1 for p in pos if p.delivery_status == "cancelled"),
            "overdue_now": sum(
                1
                for p in pos
                if p.delivery_status not in ("delivered", "cancelled")
                and p.promised_date
                and p.promised_date < today
            ),
        },
        "on_time": {
            "pct": _pct(on_final, with_date),
            "of": with_date,
            "against": "the date in force when the goods arrived",
        },
        "on_time_first": {
            "pct": _pct(on_first, first_known),
            "of": first_known,
            "against": "the first date, calculated from the quoted lead time",
        },
        "avg_days_late_when_late": round(mean(late_by), 1) if late_by else None,
        "date_moves": {"later": moves, "orders": moved_orders},
        "lead_time": {
            "actual": _spread(actual),
            "quoted_mean": round(mean(quoted), 1) if quoted else None,
            "actual_minus_quoted": round(mean(actual) - mean(quoted), 1) if actual and quoted else None,
        },
        "in_full": {"pct": None, "note": "not measured: the delivery record has no received quantity"},
        "enough": enough,
        "min_orders": min_orders,
        "note": ""
        if enough
        else f"only {n} delivered order(s): fewer than {min_orders}, too few to judge the supplier by",
        "recent": rows[-RECENT:][::-1],
    }
