"""Supplier profiles, discounts, due-diligence checks, and the sortable, filterable supplier list."""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, CatalogPrice, Offer, Supplier, SupplierCheck, SupplierDiscount

TIERS = ("vendor", "distributor", "sub_distributor", "reseller")
PAYMENT_TYPES = ("prepayment", "on_delivery", "deferred", "credit")
PARTNER_STATUSES = ("new", "approved", "preferred", "on_hold")
CHECK_RESULTS = ("working", "not_working", "under_review")
PROFILE_FIELDS = (
    "brands",
    "product_types",
    "brand_tiers",
    "stock_delivery_days",
    "payment_type",
    "contract_note",
    "has_credit_line",
    "credit_line_note",
    "rebates",
    "partner_status",
    "website",
)

_STATUS_ORDER = {s: i for i, s in enumerate(("preferred", "approved", "new", "on_hold"))}
_CHECK_ORDER = {s: i for i, s in enumerate(("working", "under_review", "unchecked", "not_working"))}
SORT_KEYS = (
    "name",
    "country",
    "deals_count",
    "age_years",
    "payment_terms_days",
    "warranty_months",
    "stock_delivery_days",
    "partner_status",
    "check",
    "catalog_lines",
    "offers",
    "brands",
)


def _need_person(name: str) -> str:
    from app.pipeline.service import PipelineError  # late: pipeline.service imports the shortlist

    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _audit(session: Session, person: str, action: str, **payload) -> None:
    session.add(AuditLog(actor="human", actor_id=person, action=action, payload=payload))


def _words(values) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
        raise ValueError("expected a list of text values")
    out: list[str] = []
    for v in values:
        v = v.strip()
        if v and v.lower() not in {o.lower() for o in out}:
            out.append(v)
    return out


def clean_profile(changes: dict) -> dict:
    """Validate and normalise the profile fields in `changes`; other keys pass through untouched."""
    out = dict(changes)
    for key in ("brands", "product_types"):
        if key in out:
            out[key] = _words(out[key])
    if "brand_tiers" in out:
        tiers = out["brand_tiers"]
        if not isinstance(tiers, dict):
            raise ValueError("brand_tiers must map a brand to a tier")
        for brand, tier in tiers.items():
            if tier not in TIERS:
                raise ValueError(f"tier for {brand!r} must be one of {', '.join(TIERS)}")
        out["brand_tiers"] = {b.strip(): t for b, t in tiers.items() if b.strip()}
    if out.get("payment_type") and out["payment_type"] not in PAYMENT_TYPES:
        raise ValueError(f"payment_type must be one of {', '.join(PAYMENT_TYPES)}")
    if out.get("partner_status") and out["partner_status"] not in PARTNER_STATUSES:
        raise ValueError(f"partner_status must be one of {', '.join(PARTNER_STATUSES)}")
    days = out.get("stock_delivery_days")
    if days is not None and (not isinstance(days, int) or days < 0 or days > 365):
        raise ValueError("stock_delivery_days must be a whole number of days, 0 to 365")
    for key in ("payment_type", "partner_status", "website", "contract_note", "credit_line_note", "rebates"):
        if key in out and isinstance(out[key], str):
            out[key] = out[key].strip() or None
    return out


# ---- checks -----------------------------------------------------------------------------------


def latest_checks(session: Session) -> dict[int, SupplierCheck]:
    out: dict[int, SupplierCheck] = {}
    for c in session.scalars(select(SupplierCheck).order_by(SupplierCheck.id)):
        out[c.supplier_id] = c
    return out


def check_dict(c: SupplierCheck) -> dict:
    return {
        "id": c.id,
        "supplier_id": c.supplier_id,
        "result": c.result,
        "checked_by": c.checked_by,
        "contact_details": c.contact_details,
        "note": c.note,
        "checked_at": c.checked_at.isoformat() if c.checked_at else None,
    }


def add_check(
    session: Session,
    supplier_id: int,
    result: str,
    checked_by: str,
    contact_details: str | None = None,
    note: str | None = None,
) -> SupplierCheck:
    by = _need_person(checked_by)
    if session.get(Supplier, supplier_id) is None:
        raise LookupError("supplier not found")
    if result not in CHECK_RESULTS:
        raise ValueError(f"result must be one of {', '.join(CHECK_RESULTS)}")
    row = SupplierCheck(
        supplier_id=supplier_id,
        result=result,
        checked_by=by,
        contact_details=(contact_details or "").strip() or None,
        note=(note or "").strip() or None,
    )
    session.add(row)
    session.flush()
    _audit(session, by, "supplier.checked", supplier_id=supplier_id, result=result)
    session.commit()
    session.refresh(row)
    return row


def checks_overview(session: Session, result: str = "") -> list[dict]:
    """Every supplier with its newest check (or none), for the Supplier checks tab."""
    latest = latest_checks(session)
    rows = []
    for s in session.scalars(select(Supplier).order_by(Supplier.name)):
        c = latest.get(s.id)
        state = c.result if c else "unchecked"
        if result and state != result:
            continue
        rows.append(
            {
                "supplier_id": s.id,
                "name": s.name,
                "country": s.country,
                "sanctioned": s.sanctioned,
                "result": state,
                "checked_by": c.checked_by if c else None,
                "checked_at": c.checked_at.isoformat() if c and c.checked_at else None,
                "contact_details": c.contact_details if c else None,
                "note": c.note if c else None,
            }
        )
    rows.sort(key=lambda r: (_CHECK_ORDER[r["result"]], r["name"].casefold()))
    return rows


def check_history(session: Session, supplier_id: int) -> list[dict]:
    rows = session.scalars(
        select(SupplierCheck)
        .where(SupplierCheck.supplier_id == supplier_id)
        .order_by(SupplierCheck.id.desc())
    )
    return [check_dict(c) for c in rows]


# ---- discounts --------------------------------------------------------------------------------


def discounts_of(session: Session, supplier_id: int) -> list[dict]:
    rows = session.scalars(
        select(SupplierDiscount)
        .where(SupplierDiscount.supplier_id == supplier_id)
        .order_by(SupplierDiscount.brand)
    )
    return [{"id": d.id, "brand": d.brand, "description": d.description} for d in rows]


def add_discount(session: Session, supplier_id: int, brand: str, description: str, changed_by: str):
    by = _need_person(changed_by)
    if session.get(Supplier, supplier_id) is None:
        raise LookupError("supplier not found")
    brand, description = brand.strip(), description.strip()
    if not brand or not description:
        raise ValueError("brand and description are required")
    row = SupplierDiscount(supplier_id=supplier_id, brand=brand, description=description)
    session.add(row)
    session.flush()
    _audit(session, by, "supplier.discount_added", supplier_id=supplier_id, brand=brand)
    session.commit()
    return row


def remove_discount(session: Session, discount_id: int, changed_by: str) -> None:
    by = _need_person(changed_by)
    row = session.get(SupplierDiscount, discount_id)
    if row is None:
        raise LookupError("discount not found")
    _audit(session, by, "supplier.discount_removed", supplier_id=row.supplier_id, brand=row.brand)
    session.delete(row)
    session.commit()


# ---- list, sorting, filters -------------------------------------------------------------------


def _rows(session: Session) -> list[dict]:
    lines = Counter(c.supplier_id for c in session.scalars(select(CatalogPrice)))
    offers = Counter(o.supplier_id for o in session.scalars(select(Offer)))
    latest = latest_checks(session)
    out = []
    for s in session.scalars(select(Supplier)):
        d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
        c = latest.get(s.id)
        d.update(
            catalog_lines=lines.get(s.id, 0),
            offers=offers.get(s.id, 0),
            check_result=c.result if c else "unchecked",
            checked_by=c.checked_by if c else None,
            checked_at=c.checked_at.isoformat() if c and c.checked_at else None,
        )
        out.append(d)
    return out


def _matches(d: dict, *, q, country, category, brand, tier, check, status) -> bool:
    if country and d["country"] != country.upper():
        return False
    if category and category not in d["categories"]:
        return False
    if brand and brand.lower() not in {b.lower() for b in d["brands"]}:
        return False
    if tier and tier not in d["brand_tiers"].values():
        return False
    if check and d["check_result"] != check:
        return False
    if status and d["partner_status"] != status:
        return False
    if q:
        hay = " ".join([d["name"], d["email"], *d["brands"], *d["product_types"]]).casefold()
        if q.strip().casefold() not in hay:
            return False
    return True


def _sort_value(d: dict, key: str):
    if key == "name":
        return d["name"].casefold()
    if key == "country":
        return d["country"]
    if key == "partner_status":
        return _STATUS_ORDER.get(d["partner_status"])
    if key == "check":
        return _CHECK_ORDER[d["check_result"]]
    if key == "brands":
        return len(d["brands"])
    return d[key]


def overview(
    session: Session,
    *,
    q: str = "",
    country: str = "",
    category: str = "",
    brand: str = "",
    tier: str = "",
    check: str = "",
    status: str = "",
    sort: str = "name",
    direction: str = "asc",
) -> list[dict]:
    if sort not in SORT_KEYS:
        raise ValueError(f"sort must be one of {', '.join(SORT_KEYS)}")
    if direction not in ("asc", "desc"):
        raise ValueError("dir must be asc or desc")
    rows = [
        d
        for d in _rows(session)
        if _matches(
            d, q=q, country=country, category=category, brand=brand, tier=tier, check=check, status=status
        )
    ]
    rows.sort(key=lambda d: d["name"].casefold())  # stable tie-break
    present = [d for d in rows if _sort_value(d, sort) is not None]
    missing = [d for d in rows if _sort_value(d, sort) is None]  # empty values go last either way
    present.sort(key=lambda d: _sort_value(d, sort), reverse=direction == "desc")
    return present + missing


def facets(session: Session, country: str = "", category: str = "") -> dict:
    """Values for the filter drop-downs. Each level only offers what exists under the levels above it:
    country, then category, then brand."""
    rows = _rows(session)

    def count(values):
        return [
            {"value": v, "count": n}
            for v, n in sorted(Counter(values).items(), key=lambda kv: kv[0].casefold())
        ]

    under_country = [d for d in rows if not country or d["country"] == country.upper()]
    under_category = [d for d in under_country if not category or category in d["categories"]]
    return {
        "countries": count(d["country"] for d in rows),
        "categories": count(c for d in under_country for c in d["categories"]),
        "brands": count(b for d in under_category for b in d["brands"]),
        "tiers": count(t for d in under_category for t in set(d["brand_tiers"].values())),
        "statuses": count(d["partner_status"] for d in under_category if d["partner_status"]),
        "checks": count(d["check_result"] for d in under_category),
    }
