"""Finds suppliers that may be one company entered twice. Three signals, none of them a verdict:

- the same tax number (as typed on the profile; a country prefix and punctuation are ignored),
- the same bank account (compared by its hash, so nothing is decrypted; accounts in force and proposed),
- the same name once legal forms, case and punctuation are ignored, or a very similar one.

The result is a list for a person to review. The code never merges, hides or blocks a supplier. A person
records "different companies" or "the same company" with a reason; the signals seen at that moment are
kept, so a new signal (say, a shared account added later) brings a dismissed pair back."""

import re
from difflib import SequenceMatcher
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Supplier, SupplierBankAccount, SupplierBankChange, SupplierDuplicateReview
from app.pipeline.service import PipelineError

SIMILAR_NAME = 0.9  # similarity of the normalised names (1.0 = identical) that counts as "similar"
MIN_TAX_LENGTH = 5
LEGAL_FORMS = {
    "gmbh", "ag", "kg", "ug", "ohg", "gesmbh", "ltd", "limited", "llc", "inc", "corp", "corporation",
    "plc", "llp", "pte", "pty", "sa", "sas", "srl", "spa", "sl", "bv", "nv", "bvba", "ab", "as", "oy",
    "aps", "doo", "dooel", "sro", "zoo", "sp", "z", "oo", "ooo", "zao", "ou", "kft", "co", "the", "and",
}  # fmt: skip
STRENGTH = {"tax_id": 3, "bank_account": 3, "name_same": 2, "name_similar": 1}
LABELS = {
    "tax_id": "same tax number",
    "bank_account": "same bank account",
    "name_same": "same name apart from legal form and spelling",
    "name_similar": "similar name",
}
VERDICTS = ("different", "same")


def name_key(name: str) -> str:
    text = re.sub(r"[.'’`]", "", name.casefold())
    tokens = [t for t in re.split(r"[^\w]+", text) if t and t not in LEGAL_FORMS]
    return " ".join(tokens)


def tax_key(tax_id: str | None) -> str | None:
    if not tax_id:
        return None
    compact = "".join(ch for ch in tax_id if ch.isalnum()).upper()
    if len(compact) > 2 and compact[:2].isalpha():
        compact = compact[2:]  # an EU style country prefix: RS100123456 and 100123456 are one number
    return compact if len(compact) >= MIN_TAX_LENGTH else None


def _person(name: str) -> str:
    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _side(s: Supplier) -> dict:
    return {"id": s.id, "name": s.name, "country": s.country, "tax_id": s.tax_id}


def _signals(session: Session, suppliers: list[Supplier]) -> dict[tuple[int, int], list[dict]]:
    found: dict[tuple[int, int], list[dict]] = {}
    by_id = {s.id: s for s in suppliers}

    def add(a: int, b: int, kind: str, detail: str) -> None:
        pair = (min(a, b), max(a, b))
        if not any(r["kind"] == kind for r in found.setdefault(pair, [])):
            found[pair].append({"kind": kind, "label": LABELS[kind], "detail": detail})

    groups: dict[str, list[int]] = {}
    for s in suppliers:
        key = tax_key(s.tax_id)
        if key:
            groups.setdefault(key, []).append(s.id)
    for key, ids in groups.items():
        for a, b in combinations(sorted(ids), 2):
            far = by_id[a].country != by_id[b].country
            add(a, b, "tax_id", f"{key}" + (" (the suppliers are in different countries)" if far else ""))

    held: dict[str, set[int]] = {}
    for h, sid in session.execute(select(SupplierBankAccount.account_hash, SupplierBankAccount.supplier_id)):
        held.setdefault(h, set()).add(sid)
    for h, sid in session.execute(
        select(SupplierBankChange.account_hash, SupplierBankChange.supplier_id).where(
            SupplierBankChange.status == "pending"
        )
    ):
        held.setdefault(h, set()).add(sid)
    for ids in held.values():
        for a, b in combinations(sorted(ids), 2):
            add(a, b, "bank_account", "one account for both (in force or proposed)")

    keys = {s.id: name_key(s.name) for s in suppliers}
    index: dict[str, set[int]] = {}
    for sid, key in keys.items():
        for token in key.split():
            if len(token) >= 3:
                index.setdefault(token, set()).add(sid)
    seen: set[tuple[int, int]] = set()
    for ids in index.values():
        for a, b in combinations(sorted(ids), 2):
            if (a, b) in seen:
                continue
            seen.add((a, b))
            ka, kb = keys[a], keys[b]
            if ka == kb:
                add(a, b, "name_same", f"“{by_id[a].name}” and “{by_id[b].name}”")
            elif SequenceMatcher(None, ka, kb).ratio() >= SIMILAR_NAME:
                add(a, b, "name_similar", f"“{by_id[a].name}” and “{by_id[b].name}”")
    return found


def _review_dict(r: SupplierDuplicateReview) -> dict:
    return {
        "id": r.id,
        "verdict": r.verdict,
        "note": r.note,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "signals": r.signals,
    }


def find(session: Session) -> list[dict]:
    """Every pair with at least one signal, strongest first, each with its review if there is one."""
    suppliers = list(session.scalars(select(Supplier).order_by(Supplier.id)))
    by_id = {s.id: s for s in suppliers}
    reviews = {
        (r.supplier_a_id, r.supplier_b_id): r for r in session.scalars(select(SupplierDuplicateReview))
    }
    out = []
    for (a, b), reasons in _signals(session, suppliers).items():
        kinds = {r["kind"] for r in reasons}
        rev = reviews.get((a, b))
        reappeared = bool(rev) and rev.verdict == "different" and not kinds <= set(rev.signals)
        out.append(
            {
                "a": _side(by_id[a]),
                "b": _side(by_id[b]),
                "reasons": reasons,
                "strength": max(STRENGTH[k] for k in kinds),
                "review": _review_dict(rev) if rev else None,
                "reappeared": reappeared,
            }
        )
    out.sort(key=lambda p: (-p["strength"], p["a"]["id"], p["b"]["id"]))
    return out


def _open(p: dict) -> bool:
    """Shown by default: not reviewed, or reviewed as the same company, or dismissed but with a new signal."""
    r = p["review"]
    return r is None or r["verdict"] == "same" or p["reappeared"]


def listing(session: Session, include_reviewed: bool = False) -> dict:
    pairs = find(session)
    shown = pairs if include_reviewed else [p for p in pairs if _open(p)]
    return {
        "pairs": shown,
        "hidden": len(pairs) - len(shown),
        "unreviewed": sum(1 for p in pairs if p["review"] is None),
        "thresholds": {"similar_name": SIMILAR_NAME, "min_tax_length": MIN_TAX_LENGTH},
    }


def for_supplier(session: Session, supplier_id: int) -> list[dict]:
    return [p for p in find(session) if supplier_id in (p["a"]["id"], p["b"]["id"]) and _open(p)]


def review(session: Session, a_id: int, b_id: int, verdict: str, note: str, by: str) -> dict:
    who = _person(by)
    if verdict not in VERDICTS:
        raise ValueError(f"the verdict must be one of: {', '.join(VERDICTS)}")
    note = note.strip()
    if len(note) < 3:
        raise ValueError("say why: a short reason is required")
    a, b = min(a_id, b_id), max(a_id, b_id)
    if a == b:
        raise ValueError("a supplier cannot be a duplicate of itself")
    pair = next((p for p in find(session) if (p["a"]["id"], p["b"]["id"]) == (a, b)), None)
    if pair is None:
        if session.get(Supplier, a) is None or session.get(Supplier, b) is None:
            raise LookupError("supplier not found")
        raise ValueError("these two suppliers share no signal, so there is nothing to review")
    kinds = sorted(r["kind"] for r in pair["reasons"])
    row = session.scalar(
        select(SupplierDuplicateReview).where(
            SupplierDuplicateReview.supplier_a_id == a, SupplierDuplicateReview.supplier_b_id == b
        )
    )
    previous = row.verdict if row else None
    if row is None:
        row = SupplierDuplicateReview(supplier_a_id=a, supplier_b_id=b, verdict=verdict, note=note[:300])
        session.add(row)
    row.verdict, row.note, row.signals, row.reviewed_by = verdict, note[:300], kinds, who
    session.add(
        AuditLog(
            actor="human",
            actor_id=who,
            action="supplier.duplicate_reviewed",
            payload={"a": a, "b": b, "verdict": verdict, "previous": previous, "signals": kinds},
        )
    )
    session.commit()
    return next(p for p in find(session) if (p["a"]["id"], p["b"]["id"]) == (a, b))


def clear_review(session: Session, review_id: int, by: str) -> None:
    who = _person(by)
    row = session.get(SupplierDuplicateReview, review_id)
    if row is None:
        raise LookupError("review not found")
    session.add(
        AuditLog(
            actor="human",
            actor_id=who,
            action="supplier.duplicate_review_removed",
            payload={"a": row.supplier_a_id, "b": row.supplier_b_id, "verdict": row.verdict},
        )
    )
    session.delete(row)
    session.commit()
