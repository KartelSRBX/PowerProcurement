"""Signals on an article, from this company's own history: is a supplier now asking more than the last price
that was paid or ordered for the same article, or promising a longer lead time than the last order took?
Plain arithmetic on orders, accepted invoices and delivery dates already in the app; no market data, no AI.
A signal is a warning for a person to look at: it never changes a score and never blocks anything.

An article is identified by its part number when the request item has one (letters and digits, case ignored),
otherwise by its description (case and spacing ignored). The last price is, in this order: the unit price on
an accepted supplier invoice that had lines ("paid"), else the unit price of the offer behind an order
("ordered"). The last lead time is the days an order actually took if it was delivered, else the lead time
that was quoted. The offer's lead time is for the whole order, so it is set against the longest last lead
among its items."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import to_eur
from app.models import Offer, OfferLine, PurchaseOrder, RequestItem, Supplier, SupplierInvoice
from app.pipeline.service import get_request, items_of


def article_key(item: RequestItem) -> str:
    if item.part_number and item.part_number.strip():
        return "pn:" + "".join(ch for ch in item.part_number.casefold() if ch.isalnum())
    return "d:" + " ".join(item.description.casefold().split())


def _history(
    session: Session, settings: Settings, exclude_request_id: int
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Latest price point and latest lead point per article over all earlier orders. They are kept apart: a
    newer order with no price for the article must not hide an older one that has it."""
    prices: dict[str, dict] = {}
    leads: dict[str, dict] = {}
    for po in session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id)):
        if po.request_id == exclude_request_id:
            continue
        offer = session.get(Offer, po.offer_id)
        sup = session.get(Supplier, po.supplier_id)
        inv = session.scalar(select(SupplierInvoice).where(SupplierInvoice.order_id == po.id))
        paid = {ln["item_id"]: ln for ln in (inv.lines or [])} if inv is not None and inv.accepted_by else {}
        lines = {
            ln.item_id: ln for ln in session.scalars(select(OfferLine).where(OfferLine.offer_id == offer.id))
        }
        ordered_on = po.created_at.date() if po.created_at else None
        if po.delivered_date and ordered_on:
            lead, lead_kind = (po.delivered_date - ordered_on).days, "actual"
        else:
            lead, lead_kind = offer.lead_time_days, "quoted"
        for item in items_of(session, po.request_id):
            key = article_key(item)
            base = {
                "order_id": po.id,
                "supplier": sup.name,
                "date": ordered_on.isoformat() if ordered_on else None,
            }
            leads[key] = base | {"lead_days": lead, "lead_kind": lead_kind}
            if item.id in paid:
                price = to_eur(paid[item.id]["unit_price"], inv.currency, settings)
                prices[key] = base | {"unit_price_eur": round(price, 4), "price_kind": "paid"}
            elif item.id in lines:
                price = to_eur(lines[item.id].unit_price, offer.currency, settings)
                prices[key] = base | {"unit_price_eur": round(price, 4), "price_kind": "ordered"}
    return prices, leads


def for_request(session: Session, settings: Settings, request_id: int) -> dict:
    """Signals for every offer on the request."""
    get_request(session, request_id)
    items = items_of(session, request_id)
    prices, lead_hist = _history(session, settings, request_id)
    price_limit, lead_pct, lead_days = (
        settings.signal_price_rise_pct,
        settings.signal_lead_rise_pct,
        settings.signal_lead_rise_days,
    )
    offers = []
    for o in session.scalars(select(Offer).where(Offer.request_id == request_id).order_by(Offer.id)):
        sup = session.get(Supplier, o.supplier_id)
        lines = {
            ln.item_id: ln for ln in session.scalars(select(OfferLine).where(OfferLine.offer_id == o.id))
        }
        rows, texts, leads = [], [], []
        for it in items:
            last = prices.get(article_key(it))
            ln = lines.get(it.id)
            row = {
                "item_id": it.id,
                "description": it.description,
                "unit_price_eur": None
                if ln is None
                else round(to_eur(ln.unit_price, o.currency, settings), 4),
                "last": last,
                "price_change_pct": None,
                "price_signal": False,
            }
            if (lp := lead_hist.get(article_key(it))) is not None:
                leads.append(lp)
            if ln is not None and last is not None and last["unit_price_eur"]:
                pct = 100 * (row["unit_price_eur"] - last["unit_price_eur"]) / last["unit_price_eur"]
                row["price_change_pct"] = round(pct, 2)
                if pct >= price_limit:
                    row["price_signal"] = True
                    texts.append(
                        f"{it.description}: unit price {row['unit_price_eur']:g} EUR is {pct:+.1f}% against "
                        f"{last['unit_price_eur']:g} EUR last {last['price_kind']} "
                        f"(order #{last['order_id']}, {last['supplier']}); threshold {price_limit:g}%"
                    )
            rows.append(row)
        lead = {
            "offer_days": o.lead_time_days,
            "last_days": None,
            "change_days": None,
            "change_pct": None,
            "signal": False,
        }
        if leads:
            ref = max(leads, key=lambda x: x["lead_days"])
            change = o.lead_time_days - ref["lead_days"]
            pct = 100 * change / ref["lead_days"] if ref["lead_days"] else None
            lead.update(
                last_days=ref["lead_days"],
                last_kind=ref["lead_kind"],
                last_order_id=ref["order_id"],
                change_days=change,
                change_pct=None if pct is None else round(pct, 1),
            )
            if change >= lead_days and (pct is None or pct >= lead_pct):
                lead["signal"] = True
                texts.append(
                    f"lead time {o.lead_time_days} days is {change} day(s) longer than the last order "
                    f"({ref['lead_days']} days {ref['lead_kind']}, order #{ref['order_id']}); "
                    f"threshold {lead_days} days and {lead_pct:g}%"
                )
        offers.append(
            {
                "offer_id": o.id,
                "supplier": sup.name,
                "items": rows,
                "lead": lead,
                "signals": texts,
                "with_history": sum(1 for r in rows if r["last"] is not None),
            }
        )
    return {
        "request_id": request_id,
        "thresholds": {"price_rise_pct": price_limit, "lead_rise_pct": lead_pct, "lead_rise_days": lead_days},
        "offers": offers,
    }
