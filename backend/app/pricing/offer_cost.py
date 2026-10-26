"""Which landed cost an offer is judged by. A person's saved calculation (Calculator tab) when it is complete
and still matches the offer's price; otherwise the old flat estimate per country, which stays as the fallback
so that every offer has a cost to rank by. The result says which of the two it used and why, so nobody reads
a rough estimate as a calculation."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import to_eur
from app.models import Offer, OfferCost, Supplier
from app.scoring.scoring import DEFAULT_LANDED_RATE, LANDED_COST_RATE, landed_cost

CALCULATION = "calculation"
FLAT = "flat estimate"
PRICE_TOLERANCE = 0.01  # the saved goods value may differ from the offer's price by 1% (rounding of rates)


@dataclass(frozen=True)
class OfferCostBasis:
    cost_eur: float
    source: str  # CALCULATION or FLAT
    note: str  # why the flat estimate was used; empty for a calculation
    breakdown: dict

    def as_dict(self) -> dict:
        return {
            "cost_eur": round(self.cost_eur, 2),
            "source": self.source,
            "note": self.note,
            "breakdown": self.breakdown,
        }


def saved_for(session: Session, offer_id: int) -> OfferCost | None:
    return session.scalar(select(OfferCost).where(OfferCost.offer_id == offer_id))


def matches_offer(saved: OfferCost, offer: Offer, settings: Settings) -> bool:
    now = to_eur(offer.total_price, offer.currency, settings)
    return abs(saved.goods_eur - now) <= PRICE_TOLERANCE * now


def cost_for(session: Session, settings: Settings, offer: Offer, supplier: Supplier) -> OfferCostBasis:
    goods_eur = to_eur(offer.total_price, offer.currency, settings)
    saved = saved_for(session, offer.id)
    why = "no calculation saved for this offer"
    if saved is not None:
        if not saved.complete:
            why = "the saved calculation is incomplete (a figure is missing)"
        elif not matches_offer(saved, offer, settings):
            why = "the offer's price changed after the calculation was saved"
        else:
            return OfferCostBasis(
                saved.landed_cost_eur,
                CALCULATION,
                "",
                {
                    "lines": saved.result["total"]["lines"],
                    "landed_cost_eur": saved.result["total"]["landed_cost_eur"],
                    "cash_out_eur": saved.result["total"]["cash_out_eur"],
                    "incoterm": saved.inputs.get("incoterm"),
                    "saved_by": saved.saved_by,
                    "saved_at": saved.saved_at.isoformat() if saved.saved_at else None,
                },
            )
    rate = LANDED_COST_RATE.get(supplier.country, DEFAULT_LANDED_RATE)
    return OfferCostBasis(
        landed_cost(goods_eur, supplier.country),
        FLAT,
        why,
        {
            "lines": [
                {"key": "goods", "label": "goods, as quoted", "amount_eur": round(goods_eur, 2), "note": ""},
                {
                    "key": "flat",
                    "label": "freight and duty, flat estimate",
                    "amount_eur": round(goods_eur * rate, 2),
                    "note": f"{rate * 100:g}% of the goods ({supplier.country}), a demo figure",
                },
            ],
            "landed_cost_eur": round(goods_eur * (1 + rate), 2),
        },
    )
