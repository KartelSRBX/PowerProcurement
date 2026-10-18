"""Step 2: which suppliers are worth asking. Deterministic: category, catalog coverage, history."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.intake.evaluate import normalize
from app.models import CatalogPrice, CustomerRequest, RequestItem, ShortlistEntry, Supplier
from app.suppliers.profile import latest_checks

MAX_SELECTED = 5


def item_text(item: RequestItem) -> str:
    return normalize(f"{item.description} {item.part_number or ''}")


def catalog_lines_for(session: Session, item: RequestItem) -> list[CatalogPrice]:
    text = item_text(item)
    return [c for c in session.scalars(select(CatalogPrice)) if normalize(c.keyword) in text]


def build_shortlist(session: Session, request: CustomerRequest) -> list[ShortlistEntry]:
    items = list(session.scalars(select(RequestItem).where(RequestItem.request_id == request.id)))
    category = request.parsed["category"]
    chosen_before = {
        e.supplier_id: e.selected
        for e in session.scalars(select(ShortlistEntry).where(ShortlistEntry.request_id == request.id))
    }  # running discovery again must not undo a person's ticks
    session.execute(delete(ShortlistEntry).where(ShortlistEntry.request_id == request.id))
    coverage: dict[int, int] = {}
    for item in items:
        for supplier_id in {c.supplier_id for c in catalog_lines_for(session, item)}:
            coverage[supplier_id] = coverage.get(supplier_id, 0) + 1
    checks = latest_checks(session)
    candidates = []
    for sup in session.scalars(select(Supplier)):
        if sup.sanctioned or category not in sup.categories or sup.id not in coverage:
            continue
        check = checks.get(sup.id)
        if check is not None and check.result == "not_working":
            continue  # the newest due-diligence check says this supplier does not work
        candidates.append((sup, coverage[sup.id]))
    candidates.sort(key=lambda sc: (-sc[1], -sc[0].deals_count, sc[0].name))
    entries = []
    for rank, (sup, covered) in enumerate(candidates, start=1):
        entries.append(
            ShortlistEntry(
                request_id=request.id,
                supplier_id=sup.id,
                covered_items=covered,
                rank=rank,
                selected=chosen_before.get(sup.id, rank <= MAX_SELECTED),
                reason=f"covers {covered}/{len(items)} items; {sup.deals_count} past deals; {sup.country}"
                + (
                    "; check under review"
                    if checks.get(sup.id) and checks[sup.id].result == "under_review"
                    else ""
                ),
            )
        )
    session.add_all(entries)
    session.commit()
    return entries
