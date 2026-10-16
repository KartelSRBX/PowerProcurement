"""Fixed demo exchange rates (see Settings). Amounts are rounded only when displayed."""

from app.config import Settings

CURRENCIES = ("RSD", "EUR", "USD")


def _per_eur(settings: Settings) -> dict[str, float]:
    return {"EUR": 1.0, "RSD": settings.fx_rsd_per_eur, "USD": settings.fx_usd_per_eur}


def convert(amount: float, src: str, dst: str, settings: Settings) -> float:
    rates = _per_eur(settings)
    if src not in rates or dst not in rates:
        raise ValueError(f"unsupported currency: {src} -> {dst}")
    return amount / rates[src] * rates[dst]


def to_eur(amount: float, currency: str, settings: Settings) -> float:
    return convert(amount, currency, "EUR", settings)
