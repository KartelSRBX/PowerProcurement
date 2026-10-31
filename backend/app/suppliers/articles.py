"""What a person knows about an article, kept where the code can warn about it: the manufacturer, whether the
article is end of life, and links to articles that can replace it. The code never decides any of this; it
only repeats it back where an offer for the article is being weighed.

There is no article master table. An article is identified by its part number when there is one (letters and
digits, case ignored), otherwise by its description (case and spacing ignored); the same key the price signals
use, so a note and a signal always speak about the same article."""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import ArticleAlternate, ArticleRecord, AuditLog, RequestItem

KINDS = ("replacement", "equivalent")


def key_of(part_number: str | None, description: str | None) -> str:
    if part_number and part_number.strip():
        return "pn:" + "".join(ch for ch in part_number.casefold() if ch.isalnum())
    return "d:" + " ".join((description or "").casefold().split())


def item_key(item: RequestItem) -> str:
    return key_of(item.part_number, item.description)


def ref(part_number: str | None, description: str | None) -> tuple[str, str]:
    """(key, label) for an article a person typed in."""
    if not (part_number and part_number.strip()) and not (description and description.strip()):
        raise ValueError("give a part number or a description of the article")
    key = key_of(part_number, description)
    if key in ("pn:", "d:"):
        raise ValueError("the part number must contain letters or digits")
    return key, (part_number or description or "").strip()[:200]


def _need_person(name: str) -> str:
    from app.pipeline.service import PipelineError  # late: pipeline.service imports the suppliers package

    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _audit(session: Session, person: str, action: str, **payload) -> None:
    session.add(AuditLog(actor="human", actor_id=person, action=action, payload=payload))


def _record_dump(r: ArticleRecord) -> dict:
    return {
        "id": r.id,
        "key": r.key,
        "label": r.label,
        "brand": r.brand,
        "eol": r.eol,
        "eol_since": r.eol_since.isoformat() if r.eol_since else None,
        "eol_note": r.eol_note,
        "set_by": r.set_by,
    }


def _alt_dump(a: ArticleAlternate) -> dict:
    return {
        "id": a.id,
        "label": a.label,
        "alternate_label": a.alternate_label,
        "key": a.key,
        "alternate_key": a.alternate_key,
        "kind": a.kind,
        "note": a.note,
        "set_by": a.set_by,
    }


def set_record(
    session: Session,
    set_by: str,
    part_number: str | None = None,
    description: str | None = None,
    brand: str | None = None,
    eol: bool = False,
    eol_since: date | None = None,
    eol_note: str = "",
) -> dict:
    by = _need_person(set_by)
    key, label = ref(part_number, description)
    brand = (brand or "").strip()[:100] or None
    if not eol and (eol_since or eol_note.strip()):
        raise ValueError("an end-of-life date or note needs the end-of-life mark to be set")
    if eol_since and eol_since > date.today():
        raise ValueError("the end-of-life date cannot be in the future; leave it empty if it is not known")
    if not eol and brand is None:
        raise ValueError("nothing to record: give a brand or mark the article end of life")
    row = session.scalar(select(ArticleRecord).where(ArticleRecord.key == key))
    before = None if row is None else {"brand": row.brand, "eol": row.eol}
    if row is None:
        row = ArticleRecord(key=key, label=label, set_by=by)
        session.add(row)
    row.label, row.brand, row.eol, row.eol_since, row.eol_note, row.set_by = (
        label,
        brand,
        eol,
        eol_since,
        eol_note.strip()[:300],
        by,
    )
    _audit(session, by, "article.record", key=key, brand=brand, eol=eol, before=before)
    session.commit()
    return _record_dump(row)


def remove_record(session: Session, record_id: int, removed_by: str) -> None:
    by = _need_person(removed_by)
    row = session.get(ArticleRecord, record_id)
    if row is None:
        raise LookupError("article record not found")
    _audit(session, by, "article.record_removed", key=row.key, brand=row.brand, eol=row.eol)
    session.delete(row)
    session.commit()


def add_alternate(
    session: Session,
    set_by: str,
    part_number: str | None,
    description: str | None,
    alt_part_number: str | None,
    alt_description: str | None,
    kind: str,
    note: str = "",
) -> dict:
    by = _need_person(set_by)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    key, label = ref(part_number, description)
    alt_key, alt_label = ref(alt_part_number, alt_description)
    if key == alt_key:
        raise ValueError("an article cannot be its own alternate")
    clash = session.scalar(
        select(ArticleAlternate).where(
            or_(
                (ArticleAlternate.key == key) & (ArticleAlternate.alternate_key == alt_key),
                (ArticleAlternate.key == alt_key) & (ArticleAlternate.alternate_key == key),
            )
        )
    )
    if clash is not None:
        raise ValueError(f"these two articles are already linked ({clash.kind}); remove that link first")
    row = ArticleAlternate(
        key=key,
        label=label,
        alternate_key=alt_key,
        alternate_label=alt_label,
        kind=kind,
        note=note.strip()[:300],
        set_by=by,
    )
    session.add(row)
    _audit(session, by, "article.alternate", key=key, alternate_key=alt_key, kind=kind)
    session.commit()
    return _alt_dump(row)


def remove_alternate(session: Session, alt_id: int, removed_by: str) -> None:
    by = _need_person(removed_by)
    row = session.get(ArticleAlternate, alt_id)
    if row is None:
        raise LookupError("link not found")
    _audit(session, by, "article.alternate_removed", key=row.key, alternate_key=row.alternate_key)
    session.delete(row)
    session.commit()


def listing(session: Session, q: str = "") -> dict:
    q = q.strip().casefold()
    records = [
        _record_dump(r)
        for r in session.scalars(select(ArticleRecord).order_by(ArticleRecord.label))
        if q in (r.label + " " + (r.brand or "")).casefold()
    ]
    alts = [
        _alt_dump(a)
        for a in session.scalars(select(ArticleAlternate).order_by(ArticleAlternate.id))
        if q in (a.label + " " + a.alternate_label).casefold()
    ]
    return {"records": records, "alternates": alts}


def about(session: Session, key: str) -> dict:
    """The record and the links of one article, each link seen from this article's side."""
    rec = session.scalar(select(ArticleRecord).where(ArticleRecord.key == key))
    links = []
    for a in session.scalars(
        select(ArticleAlternate).where(
            or_(ArticleAlternate.key == key, ArticleAlternate.alternate_key == key)
        )
    ):
        forward = a.key == key
        other_key, other = (a.alternate_key, a.alternate_label) if forward else (a.key, a.label)
        relation = (
            "equivalent"
            if a.kind == "equivalent"
            else (
                "replaced by" if forward else "replaces"
            )  # forward: the other article takes over from this one
        )
        other_rec = session.scalar(select(ArticleRecord).where(ArticleRecord.key == other_key))
        links.append(
            {
                "id": a.id,
                "relation": relation,
                "label": other,
                "note": a.note,
                "set_by": a.set_by,
                "other_eol": bool(other_rec and other_rec.eol),
            }
        )
    return {"record": None if rec is None else _record_dump(rec), "links": links}
