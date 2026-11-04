"""ABC/XYZ classes of the articles bought, from the order history.

ABC is by money: articles sorted by what was spent on them, cumulative share of the total; A while the
share before an article is under the A boundary, B under the B boundary, C after. XYZ is by how steady
the demand is: the quantity ordered per calendar month over the window (months with no order count as
zero), and the coefficient of variation (standard deviation over mean) against two boundaries. Both sets
of boundaries are Settings: the common 80/95 and 0.5/1.0 are only starting values.

Money is quantity x the unit price of the offer behind the order, in EUR at the rates in Settings. An
order whose offer has no price for an item cannot be split by article and is counted apart, not guessed.
With too little history for XYZ the article gets no XYZ class instead of a made-up one."""

import statistics
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import to_eur
from app.models import Offer, OfferLine, PurchaseOrder, RequestItem
from app.suppliers.articles import item_key

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def _months_back(today: date, n: int) -> int:
    """Index of the first month of a window of n calendar months ending with today's month."""
    return _month_index(today) - (n - 1)


def _abc(cum_before: float, settings: Settings) -> str:
    if cum_before < settings.abc_a_pct:
        return "A"
    return "B" if cum_before < settings.abc_b_pct else "C"


def _xyz(cv: float, settings: Settings) -> str:
    if cv <= settings.xyz_x_max:
        return "X"
    return "Y" if cv <= settings.xyz_y_max else "Z"


def analyse(session: Session, settings: Settings, today: date | None = None) -> dict:
    today = today or date.today()
    first = _months_back(today, settings.abc_window_months)
    articles: dict[str, dict] = {}
    seen_orders: set[int] = set()
    not_itemised = cancelled = outside = 0
    oldest: int | None = None
    for po in session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id)):
        if po.delivery_status == "cancelled":
            cancelled += 1
            continue
        placed = _aware(po.created_at).date()
        if _month_index(placed) < first:
            outside += 1
            continue
        offer = session.get(Offer, po.offer_id)
        lines = {
            ln.item_id: ln for ln in session.scalars(select(OfferLine).where(OfferLine.offer_id == offer.id))
        }
        used = False
        for item in session.scalars(select(RequestItem).where(RequestItem.request_id == po.request_id)):
            line = lines.get(item.id)
            if line is None or not item.quantity:
                continue
            used = True
            a = articles.setdefault(
                item_key(item),
                {"key": item_key(item), "label": item.description, "orders": set(), "quantity": 0.0,
                 "spend_eur": 0.0, "by_month": defaultdict(float)},
            )  # fmt: skip
            a["orders"].add(po.id)
            a["quantity"] += item.quantity
            a["spend_eur"] += to_eur(item.quantity * line.unit_price, offer.currency, settings)
            a["by_month"][_month_index(placed)] += item.quantity
        if used:
            seen_orders.add(po.id)
            oldest = _month_index(placed) if oldest is None else min(oldest, _month_index(placed))
        else:
            not_itemised += 1

    total = sum(a["spend_eur"] for a in articles.values())
    months = list(range(max(first, oldest), _month_index(today) + 1)) if oldest is not None else []
    enough = len(months) >= settings.xyz_min_months
    rows, cum = [], 0.0
    for a in sorted(articles.values(), key=lambda x: (-x["spend_eur"], x["label"])):
        share = 100 * a["spend_eur"] / total if total else 0.0
        abc = _abc(cum, settings)
        cum += share
        cv = xyz = None
        if enough:
            series = [a["by_month"].get(m, 0.0) for m in months]
            mean = statistics.fmean(series)
            cv = statistics.pstdev(series) / mean if mean else None
            xyz = _xyz(cv, settings) if cv is not None else None
        rows.append(
            {
                "key": a["key"],
                "label": a["label"],
                "orders": len(a["orders"]),
                "quantity": round(a["quantity"], 3),
                "spend_eur": round(a["spend_eur"], 2),
                "share_pct": round(share, 2),
                "cumulative_pct": round(min(cum, 100.0), 2),
                "abc": abc,
                "cv": round(cv, 3) if cv is not None else None,
                "xyz": xyz,
                "class": abc + (xyz or ""),
            }
        )
    matrix = {f"{a}{x}": {"articles": 0, "spend_eur": 0.0} for a in "ABC" for x in "XYZ-"}
    for r in rows:
        cell = matrix[r["abc"] + (r["xyz"] or "-")]
        cell["articles"] += 1
        cell["spend_eur"] = round(cell["spend_eur"] + r["spend_eur"], 2)
    return {
        "window_months": settings.abc_window_months,
        "history_months": len(months),
        "boundaries": {
            "a_pct": settings.abc_a_pct,
            "b_pct": settings.abc_b_pct,
            "x_max": settings.xyz_x_max,
            "y_max": settings.xyz_y_max,
            "xyz_min_months": settings.xyz_min_months,
        },
        "xyz_available": enough,
        "xyz_note": None
        if enough
        else f"only {len(months)} month(s) of orders in the window; XYZ needs at least "
        f"{settings.xyz_min_months}, so no article gets an XYZ class yet",
        "total_spend_eur": round(total, 2),
        "orders_used": len(seen_orders),
        "orders_not_itemised": not_itemised,
        "orders_cancelled": cancelled,
        "orders_before_window": outside,
        "rows": rows,
        "matrix": matrix,
        "note": "Goods without VAT, in EUR at the rates in Settings: quantity times the offer's unit price.",
    }


def to_xlsx(data: dict) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "ABC-XYZ"
    ws.append(
        ["Article", "Orders", "Quantity", "Spend EUR", "Share %", "Cumulative %", "ABC", "CV", "XYZ", "Class"]
    )
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in data["rows"]:
        ws.append(
            [r["label"], r["orders"], r["quantity"], r["spend_eur"], r["share_pct"], r["cumulative_pct"],
             r["abc"], r["cv"] if r["cv"] is not None else "", r["xyz"] or "", r["class"]]
        )  # fmt: skip
    m = wb.create_sheet("Matrix")
    m.append(["Class", "Articles", "Spend EUR"])
    for c in m[1]:
        c.font = Font(bold=True)
    for code, cell in data["matrix"].items():
        m.append(
            [code if not code.endswith("-") else code[0] + " (no XYZ)", cell["articles"], cell["spend_eur"]]
        )
    n = wb.create_sheet("Basis")
    b = data["boundaries"]
    for line in (
        ("Window, months", data["window_months"]),
        ("Months of orders in the window", data["history_months"]),
        ("A up to cumulative %", b["a_pct"]),
        ("B up to cumulative %", b["b_pct"]),
        ("X up to CV", b["x_max"]),
        ("Y up to CV", b["y_max"]),
        ("Orders used", data["orders_used"]),
        ("Orders not itemised (left out)", data["orders_not_itemised"]),
        ("Note", data["note"]),
        ("XYZ", data["xyz_note"] or "available"),
    ):
        n.append(list(line))
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
