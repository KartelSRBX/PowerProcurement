"""Step 3, AI part: suggest suppliers the keyword rules cannot see, and say why each shortlisted one fits.
The rules and filters ran first; the model can only add candidates that pass the same filters, always
unticked, so a person decides. It cannot add a sanctioned supplier or one whose newest check failed."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tasks import ai_enabled, run_task
from app.assist.drafts import items_text
from app.assist.schemas import SupplierPool
from app.config import Settings
from app.models import CustomerRequest, RequestItem, ShortlistEntry, Supplier
from app.rfq.templates import ItemLine
from app.suppliers.profile import latest_checks

MAX_CANDIDATES = 40
MAX_SUGGESTED = 5
AI_PREFIX = "AI suggestion: "


def _facts(s: Supplier, check: str | None) -> str:
    parts = [
        f"country {s.country}",
        f"categories {', '.join(s.categories) or '-'}",
        f"brands {', '.join(s.brands) or '-'}",
        f"product types {', '.join(s.product_types) or '-'}",
        f"{s.deals_count} past deals",
    ]
    if check:
        parts.append(f"latest check: {check.replace('_', ' ')}")
    return "; ".join(parts)


def _result(checks: dict, supplier_id: int) -> str | None:
    c = checks.get(supplier_id)
    return c.result if c else None


def augment_shortlist(
    session: Session, settings: Settings, req: CustomerRequest, items: list[RequestItem]
) -> dict:
    """{"used": bool, "suggested": int, "note": str | None}"""
    if not ai_enabled(settings):
        return {"used": False, "suggested": 0, "note": None}
    entries = list(session.scalars(select(ShortlistEntry).where(ShortlistEntry.request_id == req.id)))
    on_list = {e.supplier_id for e in entries}
    checks = latest_checks(session)
    category = req.parsed.get("category")
    suppliers = {s.id: s for s in session.scalars(select(Supplier))}

    def usable(s: Supplier) -> bool:
        c = checks.get(s.id)
        return not s.sanctioned and not (c and c.result == "not_working")

    candidates = sorted(
        (
            s
            for s in suppliers.values()
            if s.id not in on_list and usable(s) and (category == "other" or category in s.categories)
        ),
        key=lambda s: (-s.deals_count, s.name),
    )[:MAX_CANDIDATES]
    if not entries and not candidates:
        return {"used": True, "suggested": 0, "note": None}
    lines = [ItemLine(i.description, i.quantity, i.part_number) for i in items]
    result, note = run_task(
        session,
        settings,
        "supplier_pool",
        {
            "items": items_text(lines),
            "shortlisted": "\n".join(
                f"{e.supplier_id} | {suppliers[e.supplier_id].name} | "
                f"{_facts(suppliers[e.supplier_id], _result(checks, e.supplier_id))}"
                for e in entries
            )
            or "(none)",
            "candidates": "\n".join(
                f"{s.id} | {s.name} | {_facts(s, checks.get(s.id) and checks[s.id].result)}"
                for s in candidates
            )
            or "(none)",
        },
        SupplierPool,
    )
    if result is None:
        return {"used": False, "suggested": 0, "note": note}
    by_id = {e.supplier_id: e for e in entries}
    for why in result.parsed.explanations:
        entry = by_id.get(why.supplier_id)
        if entry is not None and why.reason.strip():
            entry.reason = f"{entry.reason} | AI: {why.reason.strip()}"[:300]
    allowed = {s.id for s in candidates}
    rank = max((e.rank for e in entries), default=0)
    added = 0
    for sug in result.parsed.suggestions:
        if added >= MAX_SUGGESTED:
            break
        if sug.supplier_id not in allowed or sug.supplier_id in by_id or not sug.reason.strip():
            continue
        rank += 1
        covered = len({n for n in sug.items if 1 <= n <= len(items)})
        entry = ShortlistEntry(
            request_id=req.id,
            supplier_id=sug.supplier_id,
            covered_items=covered,
            rank=rank,
            selected=False,
            reason=f"{AI_PREFIX}{sug.reason.strip()}"[:300],
        )
        session.add(entry)
        by_id[sug.supplier_id] = entry
        added += 1
    session.commit()
    return {"used": True, "suggested": added, "note": None}
