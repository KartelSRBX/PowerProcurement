"""Hints for the person who approves a letter: what differs from the plain template, and how long the
decisions take. Both read recorded text and timestamps; neither scores a letter or blocks an approval."""

import difflib
import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CustomerQuote, Letter, Rfq


def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").strip().split("\n")]


def changes(template_body: str | None, body: str) -> dict:
    """Line by line, what the text says now compared with the template for the same facts. `known` is
    False for a letter drafted before templates were kept, which cannot be compared."""
    if template_body is None:
        return {"known": False, "changed": False, "added": 0, "removed": 0, "lines": []}
    a, b = _lines(template_body), _lines(body)
    out, added, removed = [], 0, 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out += [{"op": "same", "text": t} for t in a[i1:i2]]
            continue
        out += [{"op": "del", "text": t} for t in a[i1:i2]]
        out += [{"op": "add", "text": t} for t in b[j1:j2]]
        removed += i2 - i1
        added += j2 - j1
    return {
        "known": True,
        "changed": bool(added or removed),
        "added": added,
        "removed": removed,
        "lines": out,
    }


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def _decided(session: Session):
    """(kind, row) for every letter that went through a decision."""
    for r in session.scalars(select(Rfq).where(Rfq.status.in_(("sent", "rejected")))):
        yield "rfq", r
    for q in session.scalars(select(CustomerQuote).where(CustomerQuote.status.in_(("sent", "rejected")))):
        yield "quote", q
    for lt in session.scalars(select(Letter).where(Letter.status.in_(("sent", "rejected")))):
        yield lt.kind, lt


def stats(session: Session, days: int = 30) -> dict:
    """Decisions in the last `days`: how long from the draft appearing to the decision, how often the text
    differs from the template, and whether AI drafts are changed more or less than template ones. A
    decision made before times were recorded is counted apart and has no time."""
    since = datetime.now(UTC) - timedelta(days=days)
    kinds: dict[str, dict] = {}
    source = {"AI": {"compared": 0, "changed": 0}, "template": {"compared": 0, "changed": 0}}
    untimed = 0
    for kind, row in _decided(session):
        if row.decided_at is None:
            untimed += 1
            continue
        if _aware(row.decided_at) < since:
            continue
        k = kinds.setdefault(
            kind,
            {
                "kind": kind,
                "decided": 0,
                "approved": 0,
                "rejected": 0,
                "minutes": [],
                "compared": 0,
                "changed": 0,
            },
        )
        k["decided"] += 1
        k["approved" if row.status == "sent" else "rejected"] += 1
        created = _aware(row.created_at)
        if created is not None:
            k["minutes"].append(max(0.0, (_aware(row.decided_at) - created).total_seconds() / 60))
        if row.template_body is not None:
            differs = changes(row.template_body, row.body)["changed"]
            k["compared"] += 1
            k["changed"] += differs
            s = source["AI" if (row.drafted_by or "").startswith("AI") else "template"]
            s["compared"] += 1
            s["changed"] += differs
    rows = []
    for k in sorted(kinds.values(), key=lambda x: x["kind"]):
        m = k.pop("minutes")
        k["median_minutes"] = round(statistics.median(m), 1) if m else None
        k["mean_minutes"] = round(statistics.mean(m), 1) if m else None
        k["longest_minutes"] = round(max(m), 1) if m else None
        rows.append(k)
    return {
        "days": days,
        "decided": sum(r["decided"] for r in rows),
        "kinds": rows,
        "by_source": source,
        "decided_without_time": untimed,
        "note": "Time runs from the draft appearing to the decision, so it includes waiting.",
    }
