"""Markup analytics: how often a quote is accepted at each markup, and which markup earns the most.

Plain counting, no model. A row is one quote with its outcome; "win" means the customer accepted at
the quoted price. The suggestion maximises markup x win rate (margin per euro of cost) over buckets that
have enough quotes, and falls back from customer to category to everything when data is thin."""

import math
import statistics
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import to_eur
from app.models import CustomerQuote, CustomerRequest, Outcome, QuoteHistory

BUCKET = 0.05  # markup bucket width
MAX_MARKUP = 0.60
MIN_BUCKET_N = 8  # quotes needed in a bucket before it can be suggested
MIN_SEGMENT_N = 30  # quotes needed before a customer or category is judged on its own


@dataclass(frozen=True)
class Row:
    customer: str
    category: str
    cost_eur: float
    markup: float
    outcome: str
    counter_price_eur: float | None
    price_eur: float
    source: str


def load_rows(session: Session, settings: Settings, source: str = "all") -> list[Row]:
    rows: list[Row] = []
    if source in ("all", "history", "synthetic", "import"):
        for h in session.scalars(select(QuoteHistory)):
            if source in ("all", "history") or h.source == source:
                rows.append(
                    Row(
                        h.customer,
                        h.category,
                        h.cost_eur,
                        h.markup,
                        h.outcome,
                        h.counter_price_eur,
                        h.price_eur,
                        h.source,
                    )
                )
    if source in ("all", "live"):
        for q in session.scalars(select(CustomerQuote).where(CustomerQuote.status == "sent")):
            out = session.scalars(
                select(Outcome).where(Outcome.quote_id == q.id).order_by(Outcome.id.desc()).limit(1)
            ).first()
            req = session.get(CustomerRequest, q.request_id)
            if out is None or req is None:
                continue
            counter = (
                to_eur(out.price, out.currency or q.currency, settings)
                if out.kind == "counter" and out.price
                else None
            )
            rows.append(
                Row(
                    req.sender,
                    (req.parsed or {}).get("category", "other"),
                    q.cost_eur,
                    q.markup,
                    out.kind,
                    counter,
                    to_eur(q.price, q.currency, settings),
                    "live",
                )
            )
    return rows


def bucket_of(markup: float) -> int:
    return min(int(max(markup, 0.0) / BUCKET), int(MAX_MARKUP / BUCKET) - 1)


def buckets(rows: list[Row]) -> list[dict]:
    out = []
    for i in range(int(MAX_MARKUP / BUCKET)):
        lo, hi = i * BUCKET, (i + 1) * BUCKET
        sel = [r for r in rows if bucket_of(r.markup) == i]
        n = len(sel)
        wins = sum(1 for r in sel if r.outcome == "accepted")
        rate = wins / n if n else None
        mid = (lo + hi) / 2
        out.append(
            {
                "from": round(lo, 3),
                "to": round(hi, 3),
                "n": n,
                "wins": wins,
                "win_rate": round(rate, 3) if rate is not None else None,
                "expected_margin": round(mid * rate, 4) if rate is not None else None,
                "usable": n >= MIN_BUCKET_N,
            }
        )
    return out


def fit_logistic(rows: list[Row]) -> tuple[float, float] | None:
    """Fit win probability = 1 / (1 + exp((markup - midpoint) / width)) by maximum likelihood on a grid.
    Quotes are grouped into 1%-wide markup bins first. Returns (midpoint, width) or None."""
    bins: dict[int, list[int]] = {}
    for r in rows:
        b = bins.setdefault(round(r.markup * 100), [0, 0])
        b[0] += 1
        b[1] += 1 if r.outcome == "accepted" else 0
    if len(bins) < 3:
        return None
    pts = [(k / 100, n, w) for k, (n, w) in bins.items()]
    best = None
    for mid_i in range(-60, 201):  # midpoint -0.30 .. 1.00
        mid = mid_i / 200
        for width in (0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.13, 0.17, 0.22, 0.30):
            ll = 0.0
            for m, n, w in pts:
                p = 1 / (1 + math.exp(max(-50.0, min(50.0, (m - mid) / width))))
                p = min(max(p, 1e-6), 1 - 1e-6)
                ll += w * math.log(p) + (n - w) * math.log(1 - p)
            if best is None or ll > best[0]:
                best = (ll, mid, width)
    return (best[1], best[2]) if best else None


def suggest_from(rows: list[Row]) -> dict | None:
    """Best markup = the one maximising markup x fitted win rate, never outside the markups seen."""
    if sum(1 for b in buckets(rows) if b["usable"]) < 3:
        return None
    fit = fit_logistic(rows)
    if fit is None:
        return None
    mid, width = fit
    lo = min(r.markup for r in rows)
    hi = max(r.markup for r in rows)
    grid = [i / 200 for i in range(int(lo * 200), int(hi * 200) + 1)]
    win = lambda m: 1 / (1 + math.exp(max(-50.0, min(50.0, (m - mid) / width))))  # noqa: E731
    best = max(grid, key=lambda m: m * win(m))
    return {
        "markup": round(best, 3),
        "win_rate": round(win(best), 3),
        "expected_margin": round(best * win(best), 4),
        "fit": {"midpoint": round(mid, 3), "width": round(width, 3)},
        "at_edge_of_data": best in (grid[0], grid[-1]),
        "n_segment": len(rows),
    }


def summary(rows: list[Row]) -> dict:
    n = len(rows)
    counters = [
        (r.price_eur - r.counter_price_eur) / r.price_eur for r in rows if r.counter_price_eur and r.price_eur
    ]
    return {
        "n": n,
        "win_rate": round(sum(1 for r in rows if r.outcome == "accepted") / n, 3) if n else None,
        "avg_markup": round(statistics.mean(r.markup for r in rows), 3) if n else None,
        "outcomes": {
            k: sum(1 for r in rows if r.outcome == k) for k in ("accepted", "counter", "rejected", "silence")
        },
        "avg_counter_discount": round(statistics.mean(counters), 3) if counters else None,
    }


def suggestion(rows: list[Row], customer: str | None = None, category: str | None = None) -> dict:
    """Pick the narrowest segment with enough quotes. Always says which one it used."""
    tries = []
    if customer:
        tries.append(("customer", customer, [r for r in rows if r.customer == customer]))
    if category:
        tries.append(("category", category, [r for r in rows if r.category == category]))
    tries.append(("all quotes", "", rows))
    for basis, label, seg in tries:
        if len(seg) >= MIN_SEGMENT_N or basis == "all quotes":
            s = suggest_from(seg)
            if s:
                return {**s, "basis": basis, "segment": label}
    return {
        "markup": None,
        "basis": "none",
        "segment": "",
        "n_segment": len(rows),
        "note": "not enough quotes with outcomes yet",
    }


def overview(rows: list[Row], customer: str | None = None, category: str | None = None) -> dict:
    seg = [
        r
        for r in rows
        if (not customer or r.customer == customer) and (not category or r.category == category)
    ]
    by_customer = []
    for c in sorted({r.customer for r in rows}):
        cr = [r for r in rows if r.customer == c]
        by_customer.append(
            {
                "customer": c,
                "category": cr[0].category,
                **summary(cr),
                "suggestion": suggestion(rows, customer=c, category=cr[0].category),
            }
        )
    by_category = []
    for cat in sorted({r.category for r in rows}):
        cr = [r for r in rows if r.category == cat]
        by_category.append({"category": cat, **summary(cr), "suggestion": suggestion(rows, category=cat)})
    return {
        "summary": summary(seg),
        "buckets": buckets(seg),
        "suggestion": suggestion(rows, customer=customer, category=category),
        "by_customer": by_customer,
        "by_category": by_category,
        "sources": {s: sum(1 for r in rows if r.source == s) for s in sorted({r.source for r in rows})},
        "thresholds": {"bucket": BUCKET, "min_bucket_n": MIN_BUCKET_N, "min_segment_n": MIN_SEGMENT_N},
    }
