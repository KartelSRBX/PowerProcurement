"""Supplier scoring. Plain deterministic code: same inputs, same score, every time.
AI may later explain a result in words; it never changes these numbers.

Formulas are a proposal (plan: weights price 30, lead time 20, reliability 20, terms 15,
external risk 15, adjustable). Each criterion is scored 0..100 and weighted.
"""

from dataclasses import dataclass, field

CRITERIA = ("price", "lead_time", "reliability", "terms", "external_risk")
DELIVERY = "delivery_history"  # sixth criterion: needs a weight and enough delivered orders

# Demo model of freight + duty as a share of goods value, and a country risk penalty. Proposal, not real data.
LANDED_COST_RATE = {"RS": 0.03, "DE": 0.05, "PL": 0.05, "HU": 0.05, "TR": 0.12, "CN": 0.18}
DEFAULT_LANDED_RATE = 0.10
COUNTRY_RISK_PENALTY = {"RS": 5, "DE": 0, "PL": 0, "HU": 0, "TR": 15, "CN": 20}
DEFAULT_COUNTRY_RISK = 10


@dataclass(frozen=True)
class Weights:
    price: int = 30
    lead_time: int = 20
    reliability: int = 20
    terms: int = 15
    external_risk: int = 15
    delivery_history: int = 0  # set in Settings; 0 means the criterion is not used

    def normalized(self, with_delivery: bool = False) -> dict[str, float]:
        raw = {c: getattr(self, c) for c in (*CRITERIA, DELIVERY) if c != DELIVERY or with_delivery}
        if any(v < 0 for v in raw.values()) or sum(raw.values()) == 0:
            raise ValueError("weights must be non-negative and not all zero")
        total = sum(raw.values())
        return {c: v / total for c, v in raw.items()}


@dataclass(frozen=True)
class SupplierFacts:
    country: str
    age_years: int
    vat_verified: bool
    deals_count: int
    framework_contract: bool
    payment_terms_days: int
    warranty_months: int
    sanctioned: bool
    flags: list[dict] = field(default_factory=list)
    # On-time record from delivered orders, 0..100; None when the supplier has too few orders to judge by.
    delivery_score: float | None = None
    delivery_note: str | None = None


@dataclass(frozen=True)
class OfferFacts:
    offer_id: int
    supplier_id: int
    landed_cost_eur: float
    lead_time_days: int
    covers_all_items: bool
    moq_ok: bool


@dataclass(frozen=True)
class ScoreResult:
    offer_id: int
    supplier_id: int
    excluded: str | None
    scores: dict[str, float]
    total: float
    notes: list[str]


def landed_cost(goods_eur: float, country: str) -> float:
    return goods_eur * (1 + LANDED_COST_RATE.get(country, DEFAULT_LANDED_RATE))


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def score_price(cost_eur: float, target_eur: float) -> float:
    if cost_eur <= 0 or target_eur <= 0:
        return 0.0
    return _clamp(100 * target_eur / cost_eur)


def score_lead_time(lead_days: int, days_available: int | None) -> float:
    if days_available is None:
        return _clamp(100 - min(60, lead_days))
    late = lead_days - days_available
    return 100.0 if late <= 0 else _clamp(100 - 10 * late)


def _flag_penalty(s: SupplierFacts, criterion: str) -> int:
    return sum(f["penalty"] for f in s.flags if f["criterion"] == criterion)


def score_reliability(s: SupplierFacts) -> float:
    pts = 10 + min(s.age_years, 10) * 4 + (20 if s.vat_verified else 0) + min(s.deals_count, 15) * 2
    return _clamp(pts - _flag_penalty(s, "reliability"))


def score_terms(s: SupplierFacts, moq_ok: bool) -> float:
    pts = (
        (30 if s.framework_contract else 0)
        + min(s.payment_terms_days, 60) / 60 * 30
        + min(s.warranty_months, 24) / 24 * 25
        + (15 if moq_ok else 0)
    )
    return _clamp(pts)


def score_external_risk(s: SupplierFacts) -> float:
    return _clamp(
        100 - COUNTRY_RISK_PENALTY.get(s.country, DEFAULT_COUNTRY_RISK) - _flag_penalty(s, "external_risk")
    )


def score_delivery_history(on_time_pct: float | None, on_time_first_pct: float | None) -> float | None:
    """Share of orders that came on time, averaged over the two measures: the date in force when the goods
    arrived and the first date (a supplier that keeps moving its date does not score well on the second)."""
    parts = [p for p in (on_time_pct, on_time_first_pct) if p is not None]
    return _clamp(sum(parts) / len(parts)) if parts else None


def score_offers(
    offers: list[tuple[OfferFacts, SupplierFacts]],
    target_eur: float | None,
    days_available: int | None,
    weights: Weights,
) -> list[ScoreResult]:
    """Hard filters first (sanctions, incomplete coverage), then weighted scoring. Sorted best first;
    excluded offers come last with their reason."""
    weights.normalized()  # validates
    eligible = [o for o, s in offers if not s.sanctioned and o.covers_all_items]
    reference = target_eur or (min(o.landed_cost_eur for o in eligible) if eligible else 0.0)
    results: list[ScoreResult] = []
    for offer, sup in offers:
        if sup.sanctioned:
            results.append(
                ScoreResult(offer.offer_id, offer.supplier_id, "sanctions list match", {}, 0.0, [])
            )
            continue
        if not offer.covers_all_items:
            results.append(
                ScoreResult(
                    offer.offer_id, offer.supplier_id, "does not cover every requested item", {}, 0.0, []
                )
            )
            continue
        scores = {
            "price": score_price(offer.landed_cost_eur, reference),
            "lead_time": score_lead_time(offer.lead_time_days, days_available),
            "reliability": score_reliability(sup),
            "terms": score_terms(sup, offer.moq_ok),
            "external_risk": score_external_risk(sup),
        }
        notes = [f"{f['label']} ({f['criterion']} -{f['penalty']})" for f in sup.flags]
        use_delivery = weights.delivery_history > 0 and sup.delivery_score is not None
        if use_delivery:
            scores[DELIVERY] = sup.delivery_score
        elif weights.delivery_history > 0 and sup.delivery_note:
            notes.append(sup.delivery_note)  # the weight is left out for this supplier, not guessed
        w = weights.normalized(use_delivery)
        total = sum(w[c] * scores[c] for c in w)
        results.append(ScoreResult(offer.offer_id, offer.supplier_id, None, scores, round(total, 2), notes))
    results.sort(key=lambda r: (r.excluded is not None, -r.total, r.offer_id))
    return results
