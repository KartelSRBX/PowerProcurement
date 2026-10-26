"""The landed-cost calculator for a whole order: several items, one set of shipping costs. Code does the
arithmetic (app/pricing/landed.py does it for one item); a person enters or confirms every figure. Costs that
belong to the shipment as a whole (freight, insurance, agent, transport inside the country) are split over the
items by their value, because that is the only split that needs no weights or volumes; the duty rate and
the VAT rate are per item."""

from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import CURRENCIES, to_eur
from app.models import Offer, OfferCost, OfferLine, Supplier
from app.pipeline.service import get_request, items_of
from app.pricing.landed import Landed, LandedInput, compute
from app.pricing.offer_cost import PRICE_TOLERANCE, matches_offer, saved_for

SHARED = ("origin", "freight", "insurance", "inland", "clearance", "inland_in_price")


@dataclass
class CalcLine:
    description: str
    quantity: float
    unit_price: float  # in the calculation's currency
    hs_code: str | None = None
    duty_pct: float | None = None
    vat_pct: float | None = None  # overrides the order's VAT rate for this item


@dataclass
class CalcInput:
    currency: str
    lines: list[CalcLine]
    incoterm: str | None = None
    origin: float | None = None  # shared costs, in `currency`; None means "not known"
    freight: float | None = None
    insurance: float | None = None
    insurance_pct: float | None = None
    inland: float | None = None
    clearance: float | None = None
    inland_in_price: float = 0.0
    vat_pct: float | None = None
    vat_recoverable: bool = True
    notes: list[str] = field(default_factory=list)


def calculate(inp: CalcInput, settings: Settings) -> dict:
    if inp.currency not in CURRENCIES:
        raise ValueError(f"unsupported currency {inp.currency}")
    if not inp.lines:
        raise ValueError("at least one item is needed")
    for ln in inp.lines:
        if ln.quantity <= 0:
            raise ValueError(f"quantity must be above zero: {ln.description}")
        if ln.unit_price <= 0:
            raise ValueError(f"unit price must be above zero: {ln.description}")

    def eur(v: float | None) -> float | None:
        return None if v is None else to_eur(v, inp.currency, settings)

    values = [to_eur(ln.unit_price * ln.quantity, inp.currency, settings) for ln in inp.lines]
    whole = sum(values)
    shared = {k: eur(getattr(inp, k)) for k in SHARED}
    results: list[Landed] = []
    for ln, value in zip(inp.lines, values, strict=True):
        share = value / whole

        def part(k: str, share: float = share) -> float | None:
            return None if shared[k] is None else shared[k] * share

        results.append(
            compute(
                LandedInput(
                    price_eur=value,
                    incoterm=inp.incoterm,
                    origin_eur=part("origin"),
                    freight_eur=part("freight"),
                    insurance_eur=part("insurance"),
                    insurance_pct=inp.insurance_pct,
                    inland_eur=part("inland"),
                    clearance_eur=part("clearance"),
                    inland_in_price_eur=part("inland_in_price") or 0.0,
                    duty_pct=ln.duty_pct,
                    vat_pct=ln.vat_pct if ln.vat_pct is not None else inp.vat_pct,
                    vat_recoverable=inp.vat_recoverable,
                )
            )
        )

    total = _sum(results)
    rows = []
    for ln, value, r in zip(inp.lines, values, results, strict=True):
        rows.append(
            {
                "description": ln.description,
                "quantity": ln.quantity,
                "hs_code": ln.hs_code,
                "duty_pct": ln.duty_pct,
                "value_eur": round(value, 2),
                "share_pct": round(value / whole * 100, 1),
                "landed_per_unit_eur": round(r.landed_cost_eur / ln.quantity, 4),
                "result": r.as_dict(),
            }
        )
    return {
        "currency": inp.currency,
        "incoterm": inp.incoterm,
        "lines": rows,
        "total": total.as_dict(),
        "warnings": _warnings(results, [ln.description for ln in inp.lines]) + inp.notes,
        "complete": total.complete,
        "fx": {"RSD": settings.fx_rsd_per_eur, "USD": settings.fx_usd_per_eur},
        "rounding": "Amounts are shown to the cent; totals are added before rounding",
    }


def _sum(results: list[Landed]) -> Landed:
    t = Landed()
    for r in results:
        t.customs_value_eur += r.customs_value_eur
        t.duty_eur += r.duty_eur
        t.vat_base_eur += r.vat_base_eur
        t.vat_eur += r.vat_eur
        t.landed_cost_eur += r.landed_cost_eur
        t.cash_out_eur += r.cash_out_eur
        t.complete = t.complete and r.complete
        for key in r.included_by_seller:
            if key not in t.included_by_seller:
                t.included_by_seller.append(key)
        for ln in r.lines:
            hit = next((x for x in t.lines if x.key == ln.key), None)
            if hit is None:
                t.lines.append(replace(ln))
            else:
                hit.amount_eur += ln.amount_eur
    if len(results) > 1:
        for ln in t.lines:
            ln.note = ""  # a note describes one item's figures, not the sum
    return t


def _warnings(results: list[Landed], names: list[str]) -> list[str]:
    """A warning every item shares is said once; one that only some items have names them."""
    out: list[str] = []
    for w in dict.fromkeys(w for r in results for w in r.warnings):
        who = [n for n, r in zip(names, results, strict=True) if w in r.warnings]
        out.append(w if len(who) == len(results) else f"{', '.join(who)}: {w}")
    return out


def draft_from_request(
    session: Session, settings: Settings, request_id: int, offer_id: int | None = None
) -> dict:
    """What the form starts with: the items of a request and, when an offer is chosen, its prices, currency,
    Incoterms rule and the supplier's country. The person still confirms or fills in every cost."""
    get_request(session, request_id)
    items = items_of(session, request_id)
    offers = list(session.scalars(select(Offer).where(Offer.request_id == request_id).order_by(Offer.id)))
    names = {o.supplier_id: session.get(Supplier, o.supplier_id) for o in offers}
    out: dict = {
        "request_id": request_id,
        "offers": [
            {
                "id": o.id,
                "supplier": names[o.supplier_id].name,
                "total_price": o.total_price,
                "currency": o.currency,
            }
            for o in offers
        ],
        "currency": "EUR",
        "incoterm": None,
        "origin_country": None,
        "offer_id": None,
        "notes": [],
        "lines": [
            {
                "item_id": it.id,
                "description": it.description,
                "quantity": it.quantity or 1,
                "unit_price": None,
            }
            for it in items
        ],
    }
    if offer_id is None:
        return out
    offer = next((o for o in offers if o.id == offer_id), None)
    if offer is None:
        raise LookupError(f"offer {offer_id} is not on request {request_id}")
    out["saved"] = saved_dump(saved_for(session, offer.id), offer, settings)
    out |= {
        "offer_id": offer.id,
        "currency": offer.currency,
        "incoterm": offer.incoterm,
        "origin_country": names[offer.supplier_id].country,
    }
    prices = {
        ln.item_id: ln.unit_price
        for ln in session.scalars(select(OfferLine).where(OfferLine.offer_id == offer.id))
    }
    if prices:
        for row in out["lines"]:
            row["unit_price"] = prices.get(row["item_id"])
        if any(r["unit_price"] is None for r in out["lines"]):
            out["notes"].append(
                "the offer has no price for every item: fill in the empty ones or remove them"
            )
    else:
        out["lines"] = [
            {
                "item_id": None,
                "description": "all items, offer total",
                "quantity": 1,
                "unit_price": offer.total_price,
            }
        ]
        out["notes"].append("the offer gives only a total price, so the order is calculated as one item")
    if not offer.incoterm:
        out["notes"].append("the offer states no Incoterms rule: choose one before trusting the result")
    return out


def save_for_offer(session: Session, settings: Settings, offer_id: int, inputs: dict, saved_by: str) -> dict:
    """Keep a calculation as the landed cost of one offer. Refused when the items add up to a different
    price than the offer states: that calculation is about something else."""
    person = saved_by.strip()
    if not person:
        raise ValueError("a named person is required to save a calculation")
    offer = session.get(Offer, offer_id)
    if offer is None:
        raise LookupError(f"offer {offer_id} not found")
    lines = [CalcLine(**ln) for ln in inputs["lines"]]
    rest = {k: v for k, v in inputs.items() if k != "lines"}
    result = calculate(CalcInput(lines=lines, **rest), settings)
    goods = sum(ln["value_eur"] for ln in result["lines"])
    offer_eur = to_eur(offer.total_price, offer.currency, settings)
    if abs(goods - offer_eur) > PRICE_TOLERANCE * offer_eur:
        raise ValueError(
            f"the items add up to {goods:.2f} EUR but the offer is {offer_eur:.2f} EUR: "
            "fix the prices or choose the right offer"
        )
    row = saved_for(session, offer_id)
    if row is None:
        row = OfferCost(offer_id=offer_id)
        session.add(row)
    row.inputs, row.result = inputs, result
    row.goods_eur = offer_eur
    row.landed_cost_eur = result["total"]["landed_cost_eur"]
    row.complete = result["complete"]
    row.saved_by = person
    session.commit()
    return saved_dump(row, offer, settings)


def saved_dump(row: OfferCost | None, offer: Offer, settings: Settings) -> dict | None:
    if row is None:
        return None
    return {
        "offer_id": row.offer_id,
        "inputs": row.inputs,
        "result": row.result,
        "landed_cost_eur": row.landed_cost_eur,
        "complete": row.complete,
        "matches_offer": matches_offer(row, offer, settings),
        "saved_by": row.saved_by,
        "saved_at": row.saved_at.isoformat() if row.saved_at else None,
        "used": row.complete and matches_offer(row, offer, settings),
    }


def delete_for_offer(session: Session, offer_id: int) -> None:
    row = saved_for(session, offer_id)
    if row is None:
        raise LookupError("no calculation is saved for this offer")
    session.delete(row)
    session.commit()
