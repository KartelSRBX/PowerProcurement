"""Synthetic quote history with planted patterns. Nothing here describes a real market.

Each customer has a price sensitivity: the chance of accepting a quote falls with the markup along a
logistic curve, 50% at `midpoint`, steeper when `width` is small. Customers differ on purpose, so
analytics have something to find, and the test checks that they find it."""

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import QuoteHistory


@dataclass(frozen=True)
class Profile:
    customer: str
    category: str
    midpoint: float  # markup at which half of the quotes are accepted
    width: float  # smaller = reacts more sharply to markup
    quotes: int


PROFILES = (
    Profile("buyer@brightlabs.example", "electronics", 0.12, 0.04, 90),  # sensitive: low markup wins
    Profile("purchasing@rhein-embedded.example", "electronics", 0.22, 0.06, 90),
    Profile("nabavka@dunavtech.example", "electronics", 0.30, 0.06, 80),
    Profile("it@northwind-trade.example", "it_hardware", 0.34, 0.07, 90),
    Profile("office@sumadija-kancelarija.example", "it_hardware", 0.26, 0.06, 80),
    Profile("admin@zlatibor-hotel.example", "other", 0.40, 0.08, 80),  # insensitive: high markup still wins
    Profile("shop@adriatic-makers.example", "other", 0.18, 0.05, 90),
)
MARKUP_RANGE = (0.0, 0.45)


def win_probability(markup: float, p: Profile) -> float:
    return 1 / (1 + math.exp((markup - p.midpoint) / p.width))


def best_markup(p: Profile, step: float = 0.005) -> float:
    """The markup that maximises markup x win probability, i.e. margin per euro of cost."""
    grid = [i * step for i in range(int(MARKUP_RANGE[1] / step) + 1)]
    return max(grid, key=lambda m: m * win_probability(m, p))


def generate(seed: int = 7, today: date | None = None) -> list[QuoteHistory]:
    rng = random.Random(seed)
    today = today or date.today()
    rows: list[QuoteHistory] = []
    for p in PROFILES:
        for _ in range(p.quotes):
            markup = round(rng.uniform(*MARKUP_RANGE), 3)
            cost = round(math.exp(rng.uniform(math.log(200), math.log(20000))), 2)
            price = round(cost * (1 + markup), 2)
            r = rng.random()
            counter = None
            if r < win_probability(markup, p):
                outcome = "accepted"
            else:
                outcome = rng.choices(("counter", "rejected", "silence"), weights=(30, 45, 25))[0]
                if outcome == "counter":
                    counter = round(price * (1 - rng.uniform(0.03, 0.12)), 2)
            rows.append(
                QuoteHistory(
                    customer=p.customer,
                    category=p.category,
                    cost_eur=cost,
                    markup=markup,
                    price_eur=price,
                    outcome=outcome,
                    counter_price_eur=counter,
                    quoted_at=today - timedelta(days=rng.randint(1, 540)),
                    source="synthetic",
                )
            )
    return rows


def load_synthetic(session: Session, seed: int = 7) -> int:
    """Insert the synthetic history once. Returns how many rows were added (0 if already there)."""
    if session.scalar(
        select(func.count()).select_from(QuoteHistory).where(QuoteHistory.source == "synthetic")
    ):
        return 0
    rows = generate(seed)
    session.add_all(rows)
    session.commit()
    return len(rows)
