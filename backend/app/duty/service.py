"""The duty registry: load a customs tariff, search it, read the rates for a code and an origin.
The rows come from the official tariff and carry its name and date; a person starts every load.
Nothing here decides which rate applies to a purchase: a preferential rate needs proof of origin, so
it is shown next to the general rate and the choice is made by whoever prepares the calculation."""

import csv
import io
import json
import re
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.duty.parser import DutyLine
from app.models import AuditLog, DutyRate

COLUMNS = [
    "code",
    "description",
    "heading",
    "unit",
    "mfn_rate",
    "mfn_text",
    "has_exceptions",
    "notes",
    "agreements",
]
MAX_ROWS = 50_000
# who is covered by which agreement key of the tariff. SSP is the Stabilisation and Association Agreement
# with the EU (the tariff's ССП column); CEFTA lists its parties in the tariff; EAEU and EFTA are stored
# per country as "EAEU:RU", "EFTA:CH".
EU = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
CEFTA = {"AL", "BA", "MK", "MD", "ME", "XK"}
DIRECT = {"TR", "GB", "CN", "AE", "EG"}
EAEU = {"AM", "BY", "KG", "KZ", "RU"}
EFTA = {"IS", "NO", "CH", "LI"}


class DutyError(Exception):
    pass


def normalize_code(q: str) -> str:
    return re.sub(r"[\s.\-]", "", q)


def to_csv(lines: list[DutyLine]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for ln in lines:
        w.writerow(
            [
                ln.code,
                ln.description,
                ln.heading,
                ln.unit,
                "" if ln.mfn_rate is None else ln.mfn_rate,
                ln.mfn_text,
                int(ln.has_exceptions),
                ln.notes,
                json.dumps(ln.agreements, ensure_ascii=False),
            ]
        )
    return out.getvalue()


def lines_from_csv(text: str) -> list[DutyLine]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or not {"code", "description"} <= set(reader.fieldnames):
        raise DutyError("the file needs at least the columns code and description")
    out = []
    for n, row in enumerate(reader, start=2):
        code = normalize_code(row["code"] or "")
        if not re.fullmatch(r"\d{10}", code):
            raise DutyError(f"line {n}: the code '{row['code']}' is not 10 digits")
        try:
            agreements = json.loads(row.get("agreements") or "{}")
            rate = row.get("mfn_rate") or ""
            mfn = float(rate.replace(",", ".")) if rate.strip() else None
        except ValueError as exc:
            raise DutyError(f"line {n}: a rate or the agreements cell could not be read") from exc
        if not isinstance(agreements, dict) or any(
            isinstance(v, bool) or not isinstance(v, (int, float, str)) for v in agreements.values()
        ):
            raise DutyError(f"line {n}: agreements must be a JSON object of partner and rate")
        if mfn is not None and not 0 <= mfn <= 1000:
            raise DutyError(f"line {n}: the duty {mfn:g}% is outside 0-1000")
        out.append(
            DutyLine(
                code=code,
                description=(row["description"] or "").strip(),
                heading=(row.get("heading") or "").strip(),
                level=0,
                unit=(row.get("unit") or "").strip(),
                mfn_rate=mfn,
                mfn_text=(row.get("mfn_text") or "").strip(),
                agreements=agreements,
                has_exceptions=(row.get("has_exceptions") or "0").strip() in ("1", "true", "True"),
                notes=(row.get("notes") or "").strip(),
            )
        )
    return out


def import_lines(
    session: Session, lines: list[DutyLine], source: str, rate_date: date | None, imported_by: str
) -> dict:
    """Replace the registry with these lines (a new tariff year replaces the old one as a whole)."""
    by = (imported_by or "").strip()
    if not by:
        raise DutyError("a named person is required to load a tariff")
    if not source.strip():
        raise DutyError("say which tariff this is (its name or the official gazette)")
    if not lines:
        raise DutyError("no tariff lines were found, so the registry was left as it was")
    if len(lines) > MAX_ROWS:
        raise DutyError(f"more than {MAX_ROWS} lines: this does not look like one tariff")
    codes = [ln.code for ln in lines]
    if len(set(codes)) != len(codes):
        raise DutyError("some codes appear twice, so the registry was left as it was")
    before = session.scalar(select(func.count()).select_from(DutyRate)) or 0
    session.execute(delete(DutyRate))
    session.add_all(
        DutyRate(
            code=ln.code,
            description=ln.description[:1000],
            heading=ln.heading[:300],
            unit=ln.unit[:8],
            mfn_rate=ln.mfn_rate,
            mfn_text=ln.mfn_text[:200],
            agreements=ln.agreements,
            has_exceptions=ln.has_exceptions,
            notes=ln.notes,
            source=source.strip()[:200],
            rate_date=rate_date,
            imported_by=by,
        )
        for ln in lines
    )
    session.add(
        AuditLog(
            actor="human",
            actor_id=by,
            action="duties.imported",
            payload={"rows": len(lines), "replaced": before, "source": source.strip()},
        )
    )
    session.commit()
    return summary(session)


def summary(session: Session) -> dict:
    rows = session.scalar(select(func.count()).select_from(DutyRate)) or 0
    if not rows:
        return {
            "rows": 0,
            "source": None,
            "rate_date": None,
            "imported_by": None,
            "imported_at": None,
            "to_check": 0,
        }
    first = session.scalar(select(DutyRate).order_by(DutyRate.id).limit(1))
    to_check = sum(
        1
        for r in session.scalars(select(DutyRate))
        if r.mfn_rate is None or r.has_exceptions or any(isinstance(v, str) for v in r.agreements.values())
    )
    return {
        "rows": rows,
        "source": first.source,
        "rate_date": first.rate_date.isoformat() if first.rate_date else None,
        "imported_by": first.imported_by,
        "imported_at": first.imported_at.isoformat() if first.imported_at else None,
        "to_check": to_check,
    }


def _dump(r: DutyRate) -> dict:
    return {
        "code": r.code,
        "code_text": f"{r.code[:4]} {r.code[4:6]} {r.code[6:8]} {r.code[8:]}",
        "description": r.description,
        "heading": r.heading,
        "unit": r.unit,
        "mfn_rate": r.mfn_rate,
        "mfn_text": r.mfn_text,
        "agreements": r.agreements,
        "has_exceptions": r.has_exceptions,
        "notes": r.notes,
        "source": r.source,
        "rate_date": r.rate_date.isoformat() if r.rate_date else None,
    }


def search(session: Session, q: str, limit: int = 50) -> list[dict]:
    q = q.strip()
    limit = max(1, min(limit, 200))
    if not q:
        return []
    stmt = select(DutyRate).order_by(DutyRate.code).limit(limit)
    digits = normalize_code(q)
    if digits.isdigit():
        stmt = stmt.where(DutyRate.code.startswith(digits))
    else:
        for word in q.lower().split():
            like = f"%{word}%"
            stmt = stmt.where(func.lower(DutyRate.description + " " + DutyRate.heading).like(like))
    return [_dump(r) for r in session.scalars(stmt)]


def get(session: Session, code: str) -> DutyRate:
    row = session.scalar(select(DutyRate).where(DutyRate.code == normalize_code(code)))
    if row is None:
        raise LookupError("this code is not in the registry")
    return row


def rates_for(row: DutyRate, origin: str | None = None) -> dict:
    """The general rate and, for an origin country, the preferential rate that country's agreement offers.
    Both are returned; applying a preference needs proof of origin and is a person's choice."""
    origin = (origin or "").strip().upper()
    key = None
    if origin in EU:
        key = "SSP"
    elif origin in CEFTA:
        key = "CEFTA"
    elif origin in DIRECT:
        key = origin
    elif origin in EAEU:
        key = f"EAEU:{origin}"
    elif origin in EFTA:
        key = f"EFTA:{origin}"
    pref = None
    if key and key in row.agreements:
        v = row.agreements[key]
        pref = {"agreement": key, "rate": v if isinstance(v, (int, float)) else None, "text": str(v)}
    notes = []
    if row.mfn_rate is None:
        notes.append("the general duty is not a plain percentage: read the tariff line")
    if pref and pref["rate"] is None:
        notes.append("the preferential rate is not a plain percentage: read the tariff line")
    if row.has_exceptions:
        notes.append("the tariff line has sub-cases with their own rates: " + row.notes)
    if pref:
        notes.append("a preferential rate needs proof of origin")
    check = row.mfn_rate is None or row.has_exceptions or (pref is not None and pref["rate"] is None)
    return {
        "code": row.code,
        "origin": origin or None,
        "mfn": {"rate": row.mfn_rate, "text": row.mfn_text},
        "preferential": pref,
        "needs_check": check,
        "notes": notes,
        "source": row.source,
        "rate_date": row.rate_date.isoformat() if row.rate_date else None,
    }
