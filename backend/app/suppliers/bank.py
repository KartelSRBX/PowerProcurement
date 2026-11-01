"""Supplier bank details. The classic payment fraud is a mail that says "our account has changed".
So here an account is never typed straight in: one person proposes it together with a record of the
call that confirmed it (who at the supplier said so, and where the number called came from: never the
mail that asked for the change), and a different person approves or rejects. Until then the old
account stays in force. Every step is logged.

The account is stored encrypted; a hash of it (letters and digits, case ignored) lets two suppliers
with the same account be found without opening it. Without sign-in the app only knows the name a
person typed, so this is a process aid, not a lock: see docs/decisions/0020-supplier-bank-details.md."""

import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditLog, Supplier, SupplierBankAccount, SupplierBankChange
from app.pipeline.service import PipelineError
from app.runtime import vault as crypto

CALLBACK_SOURCES = {
    "contract": "the contract or an order form",
    "verified_record": "an earlier record that was verified",
    "official_website": "the supplier's official website",
    "other": "another source (explain)",
}
RECENT_DAYS = 30  # a change this recent is shown as a warning wherever the account is used


def _person(name: str) -> str:
    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _audit(session: Session, person: str, action: str, **payload) -> None:
    session.add(AuditLog(actor="human", actor_id=person, action=action, payload=payload))


def normalize(account: str) -> str:
    return "".join(ch for ch in account if ch.isalnum()).upper()


def iban_ok(compact: str) -> bool:
    """The standard mod-97 check on an IBAN written without spaces."""
    if not (15 <= len(compact) <= 34) or not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    moved = compact[4:] + compact[:4]
    digits = "".join(str(int(ch, 36)) for ch in moved)
    return int(digits) % 97 == 1


def classify(account: str) -> tuple[str, str]:
    """(kind, normalized). An IBAN must pass its check digits; otherwise a domestic account number of digits
    and dashes is accepted as typed."""
    raw = account.strip()
    if not raw:
        raise ValueError("the account number is required")
    compact = normalize(raw)
    if compact[:2].isalpha() and compact[2:4].isdigit():
        if not iban_ok(compact):
            raise ValueError(
                "this looks like an IBAN but its check digits are wrong: check it for a typing error"
            )
        return "iban", compact
    if set(raw) <= set("0123456789- ") and 8 <= len(compact) <= 24:
        return "domestic", compact
    raise ValueError("give an IBAN, or a domestic account number of digits and dashes")


def _same_name(a: str, b: str) -> bool:
    x, y = (
        "".join(ch for ch in a.casefold() if ch.isalnum()),
        "".join(ch for ch in b.casefold() if ch.isalnum()),
    )
    return bool(x and y) and (x in y or y in x)


def _hash(compact: str) -> str:
    return hashlib.sha256(compact.encode()).hexdigest()


def _read(settings: Settings, token: str) -> str | None:
    plain = crypto.decrypt(settings, token)
    return plain


def _pending(session: Session, supplier_id: int) -> SupplierBankChange | None:
    return session.scalar(
        select(SupplierBankChange).where(
            SupplierBankChange.supplier_id == supplier_id, SupplierBankChange.status == "pending"
        )
    )


def _change_dict(settings: Settings, c: SupplierBankChange) -> dict:
    return {
        "id": c.id,
        "supplier_id": c.supplier_id,
        "account": _read(settings, c.account_encrypted),
        "kind": c.kind,
        "holder": c.holder,
        "bank_name": c.bank_name,
        "swift": c.swift,
        "reason": c.reason,
        "warnings": c.warnings,
        "proposed_by": c.proposed_by,
        "proposed_at": c.proposed_at.isoformat() if c.proposed_at else None,
        "callback_by": c.callback_by,
        "callback_person": c.callback_person,
        "callback_source": c.callback_source,
        "callback_source_label": CALLBACK_SOURCES.get(c.callback_source, c.callback_source),
        "callback_on": c.callback_on.isoformat(),
        "callback_note": c.callback_note,
        "status": c.status,
        "decided_by": c.decided_by,
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "decision_comment": c.decision_comment,
    }


def view(session: Session, settings: Settings, supplier_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    sup = session.get(Supplier, supplier_id)
    if sup is None:
        raise LookupError("supplier not found")
    acc = session.scalar(select(SupplierBankAccount).where(SupplierBankAccount.supplier_id == supplier_id))
    current = None
    if acc is not None:
        since = acc.confirmed_at.date() if acc.confirmed_at else today
        current = {
            "account": _read(settings, acc.account_encrypted),
            "kind": acc.kind,
            "holder": acc.holder,
            "bank_name": acc.bank_name,
            "swift": acc.swift,
            "confirmed_by": acc.confirmed_by,
            "confirmed_at": acc.confirmed_at.isoformat() if acc.confirmed_at else None,
            "days_in_force": (today - since).days,
            "recent": (today - since).days < RECENT_DAYS,
            "change_id": acc.change_id,
        }
    pending = _pending(session, supplier_id)
    history = session.scalars(
        select(SupplierBankChange)
        .where(SupplierBankChange.supplier_id == supplier_id, SupplierBankChange.status != "pending")
        .order_by(SupplierBankChange.id.desc())
        .limit(10)
    )
    return {
        "supplier_id": supplier_id,
        "current": current,
        "pending": None if pending is None else _change_dict(settings, pending),
        "history": [_change_dict(settings, h) for h in history],
        "callback_sources": CALLBACK_SOURCES,
        "recent_days": RECENT_DAYS,
    }


def propose(
    session: Session,
    settings: Settings,
    supplier_id: int,
    proposed_by: str,
    account: str,
    holder: str,
    reason: str,
    callback_by: str,
    callback_person: str,
    callback_source: str,
    callback_on: date,
    callback_note: str = "",
    bank_name: str | None = None,
    swift: str | None = None,
) -> dict:
    by = _person(proposed_by)
    sup = session.get(Supplier, supplier_id)
    if sup is None:
        raise LookupError("supplier not found")
    kind, compact = classify(account)
    holder, reason = holder.strip(), reason.strip()
    if not holder:
        raise ValueError("the account holder (beneficiary) is required")
    if len(reason) < 3:
        raise ValueError("say why the account is being set or changed")
    cb_by, cb_person = _person(callback_by), callback_person.strip()
    if not cb_person:
        raise ValueError("record who at the supplier confirmed the account on the call")
    if callback_source not in CALLBACK_SOURCES:
        raise ValueError(f"the number called must come from one of: {', '.join(CALLBACK_SOURCES)}")
    note = callback_note.strip()
    if callback_source == "other" and len(note) < 3:
        raise ValueError("explain where the number you called came from")
    if callback_on > date.today():
        raise ValueError("the call cannot be dated in the future")
    swift = (swift or "").strip().upper() or None
    if swift and not (len(swift) in (8, 11) and swift.isalnum()):
        raise ValueError("a SWIFT/BIC code has 8 or 11 letters and digits")
    if _pending(session, supplier_id) is not None:
        raise PipelineError("a proposal for this supplier is already waiting for a second person")
    warnings = []
    if kind == "iban" and compact[:2] != sup.country.upper():
        warnings.append(
            f"the IBAN is from {compact[:2]} but the supplier is registered in {sup.country.upper()}"
        )
    if not _same_name(holder, sup.name):
        warnings.append(f"the account holder “{holder}” does not match the supplier name “{sup.name}”")
    clash = session.scalars(
        select(SupplierBankAccount).where(
            SupplierBankAccount.account_hash == _hash(compact), SupplierBankAccount.supplier_id != supplier_id
        )
    ).first()
    if clash is not None:
        other = session.get(Supplier, clash.supplier_id)
        warnings.append(f"this account is already used by another supplier: {other.name}")
    cur = session.scalar(select(SupplierBankAccount).where(SupplierBankAccount.supplier_id == supplier_id))
    if cur is not None and cur.account_hash == _hash(compact):
        raise ValueError("this is already the account in force")
    row = SupplierBankChange(
        supplier_id=supplier_id,
        account_encrypted=crypto.encrypt(settings, compact),
        account_hash=_hash(compact),
        kind=kind,
        holder=holder[:200],
        bank_name=(bank_name or "").strip()[:200] or None,
        swift=swift,
        reason=reason[:300],
        warnings=warnings,
        proposed_by=by,
        callback_by=cb_by,
        callback_person=cb_person[:200],
        callback_source=callback_source,
        callback_on=callback_on,
        callback_note=note[:300],
    )
    session.add(row)
    session.flush()
    _audit(
        session, by, "bank.proposed", supplier_id=supplier_id, change_id=row.id, kind=kind, warnings=warnings
    )
    session.commit()
    return _change_dict(settings, row)


def decide(
    session: Session, settings: Settings, change_id: int, decided_by: str, approve: bool, comment: str = ""
) -> dict:
    by = _person(decided_by)
    row = session.get(SupplierBankChange, change_id)
    if row is None:
        raise LookupError("proposal not found")
    if row.status != "pending":
        raise PipelineError(f"this proposal is already {row.status}")
    if by.casefold() == row.proposed_by.casefold():
        raise PipelineError("a different person has to decide: the one who proposed it cannot approve it")
    comment = comment.strip()
    if not approve and len(comment) < 3:
        raise ValueError("say why it is rejected")
    row.status = "approved" if approve else "rejected"
    row.decided_by, row.decided_at, row.decision_comment = by, datetime.now(UTC), comment[:300] or None
    if approve:
        acc = session.scalar(
            select(SupplierBankAccount).where(SupplierBankAccount.supplier_id == row.supplier_id)
        )
        fields = dict(
            account_encrypted=row.account_encrypted,
            account_hash=row.account_hash,
            kind=row.kind,
            holder=row.holder,
            bank_name=row.bank_name,
            swift=row.swift,
            change_id=row.id,
            confirmed_by=by,
            confirmed_at=datetime.now(UTC),
        )
        if acc is None:
            session.add(SupplierBankAccount(supplier_id=row.supplier_id, **fields))
        else:
            for k, v in fields.items():
                setattr(acc, k, v)
    _audit(
        session,
        by,
        "bank.approved" if approve else "bank.rejected",
        supplier_id=row.supplier_id,
        change_id=row.id,
        proposed_by=row.proposed_by,
        comment=comment,
    )
    session.commit()
    return _change_dict(settings, row)


def withdraw(session: Session, settings: Settings, change_id: int, by: str) -> dict:
    who = _person(by)
    row = session.get(SupplierBankChange, change_id)
    if row is None:
        raise LookupError("proposal not found")
    if row.status != "pending":
        raise PipelineError(f"this proposal is already {row.status}")
    if who.casefold() != row.proposed_by.casefold():
        raise PipelineError("only the person who proposed it can withdraw it; anyone else can reject it")
    row.status, row.decided_by, row.decided_at = "withdrawn", who, datetime.now(UTC)
    _audit(session, who, "bank.withdrawn", supplier_id=row.supplier_id, change_id=row.id)
    session.commit()
    return _change_dict(settings, row)


def pending_list(session: Session, settings: Settings) -> list[dict]:
    rows = session.scalars(
        select(SupplierBankChange)
        .where(SupplierBankChange.status == "pending")
        .order_by(SupplierBankChange.id)
    )
    out = []
    for r in rows:
        d = _change_dict(settings, r)
        d["supplier"] = session.get(Supplier, r.supplier_id).name
        out.append(d)
    return out
