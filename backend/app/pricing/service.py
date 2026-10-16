"""Step 3: target prices. The source is a plug-in; the demo source is the synthetic price lists.
Every observation keeps its source, time, currency, MOQ and validity, and is 'unconfirmed'."""

from statistics import median

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import to_eur
from app.models import MarketPrice, RequestItem
from app.suppliers.shortlist import catalog_lines_for


def fetch_target_prices(session: Session, settings: Settings, request_id: int) -> dict[int, float | None]:
    """Returns {item_id: target unit price in EUR or None if nothing found}."""
    items = list(session.scalars(select(RequestItem).where(RequestItem.request_id == request_id)))
    session.execute(delete(MarketPrice).where(MarketPrice.request_item_id.in_([i.id for i in items])))
    targets: dict[int, float | None] = {}
    for item in items:
        lines = catalog_lines_for(session, item)
        for c in lines:
            session.add(
                MarketPrice(
                    request_item_id=item.id,
                    source=c.source,
                    unit_price=c.unit_price,
                    currency=c.currency,
                    moq=c.moq,
                    valid_until=c.valid_until,
                    confirmed=False,
                )
            )
        eur = [to_eur(c.unit_price, c.currency, settings) for c in lines]
        targets[item.id] = round(median(eur), 6) if eur else None
    session.commit()
    return targets


def target_total_eur(session: Session, request_id: int, targets: dict[int, float | None]) -> float | None:
    """Sum of qty x target for all items, or None if any item has no target or no quantity."""
    items = list(session.scalars(select(RequestItem).where(RequestItem.request_id == request_id)))
    if not items or any(targets.get(i.id) is None or i.quantity is None for i in items):
        return None
    return sum(i.quantity * targets[i.id] for i in items)  # type: ignore[operator]
