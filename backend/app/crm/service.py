"""Read models and small writes behind the CRM windows: mail feed, message analytics, supplier
storage, article matching and quote preview. Pure bookkeeping; no AI and nothing is sent here."""

import statistics
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.currency import convert, to_eur
from app.intake.evaluate import load_gold, normalize
from app.models import (
    AuditLog,
    CatalogPrice,
    CustomerQuote,
    CustomerRequest,
    InboxEmail,
    Letter,
    Offer,
    Outcome,
    PurchaseOrder,
    Rfq,
    Supplier,
)
from app.pipeline.service import PipelineError, get_request, items_of
from app.scoring.scoring import landed_cost
from app.suppliers import profile
from app.suppliers.shortlist import catalog_lines_for


def _need_person(name: str) -> str:
    if not name or not name.strip():
        raise PipelineError("a named person is required for this action")
    return name.strip()


def _audit(session: Session, person: str, action: str, **payload) -> None:
    session.add(AuditLog(actor="human", actor_id=person, action=action, payload=payload))


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---- Mail -------------------------------------------------------------------------------------


def store_raw_email(session: Session, mail, source: str) -> InboxEmail:
    """Keep the raw message so it is visible even when no AI parsed it. Idempotent on Message-ID."""
    row = session.scalar(select(InboxEmail).where(InboxEmail.message_id == mail.message_id))
    if row:
        return row
    row = InboxEmail(
        message_id=mail.message_id,
        sender=mail.sender,
        subject=mail.subject,
        body=mail.body,
        received_at=mail.received_at,
        source=source,
    )
    session.add(row)
    session.commit()
    return row


def load_demo_inbox(session: Session) -> int:
    """Add the 16 synthetic gold-set emails as raw, unparsed mail. Returns how many were new."""
    added = 0
    for case in load_gold():
        message_id = f"demo-gold-{case['id']}"
        if session.scalar(select(InboxEmail).where(InboxEmail.message_id == message_id)):
            continue
        day = date.fromisoformat(case["received_date"])
        session.add(
            InboxEmail(
                message_id=message_id,
                sender=case["from"],
                subject=case["subject"],
                body=case["body"],
                received_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC),
                source="demo",
            )
        )
        added += 1
    session.commit()
    return added


def _parsed_brief(req: CustomerRequest | None) -> dict | None:
    if req is None:
        return None
    p = req.parsed or {}
    return {
        "request_id": req.id,
        "request_status": req.status,
        "confidence": req.confidence,
        "language": p.get("language"),
        "category": p.get("category"),
        "items": len(p.get("items") or []),
        "model": req.model,
    }


def mail_feed(session: Session, folder: str = "all", q: str = "", limit: int = 300) -> list[dict]:
    items: list[dict] = []
    requests = {r.message_id: r for r in session.scalars(select(CustomerRequest))}
    seen: set[str] = set()
    if folder in ("all", "in"):
        for e in session.scalars(select(InboxEmail)):
            seen.add(e.message_id)
            req = requests.get(e.message_id)
            items.append(
                {
                    "key": f"in:{e.id}",
                    "direction": "in",
                    "kind": "email",
                    "id": e.id,
                    "counterparty": e.sender,
                    "subject": e.subject,
                    "body": e.body,
                    "at": _iso(e.received_at),
                    "status": req.status if req else "unparsed",
                    "source": e.source,
                    "message_id": e.message_id,
                    "request": _parsed_brief(req),
                }
            )
        for mid, req in requests.items():
            if mid in seen:
                continue
            items.append(
                {
                    "key": f"req:{req.id}",
                    "direction": "in",
                    "kind": "email",
                    "id": req.id,
                    "counterparty": req.sender,
                    "subject": req.subject,
                    "body": req.body,
                    "at": _iso(req.received_at),
                    "status": req.status,
                    "source": "manual" if mid.startswith("manual-") else "parsed",
                    "message_id": mid,
                    "request": _parsed_brief(req),
                }
            )
    if folder in ("all", "out"):
        names = {s.id: s for s in session.scalars(select(Supplier))}
        for r in session.scalars(select(Rfq)):
            sup = names[r.supplier_id]
            items.append(
                {
                    "key": f"rfq:{r.id}",
                    "direction": "out",
                    "kind": "rfq",
                    "id": r.id,
                    "counterparty": f"{sup.name} <{sup.email}>",
                    "subject": r.subject,
                    "body": r.body,
                    "at": _iso(r.created_at),
                    "status": r.status,
                    "approved_by": r.decided_by,
                    "request": {"request_id": r.request_id},
                }
            )
        for qt in session.scalars(select(CustomerQuote)):
            req = session.get(CustomerRequest, qt.request_id)
            items.append(
                {
                    "key": f"quote:{qt.id}",
                    "direction": "out",
                    "kind": "quote",
                    "id": qt.id,
                    "counterparty": req.sender if req else "",
                    "subject": qt.subject,
                    "body": qt.body,
                    "at": _iso(qt.created_at),
                    "status": qt.status,
                    "approved_by": qt.decided_by,
                    "request": {"request_id": qt.request_id},
                }
            )
        for lt in session.scalars(select(Letter)):
            sup = names.get(lt.supplier_id) if lt.supplier_id else None
            items.append(
                {
                    "key": f"letter:{lt.id}",
                    "direction": "out",
                    "kind": lt.kind,
                    "id": lt.id,
                    "counterparty": f"{sup.name} <{sup.email}>" if sup else lt.to_email,
                    "subject": lt.subject,
                    "body": lt.body,
                    "at": _iso(lt.created_at),
                    "status": lt.status,
                    "approved_by": lt.decided_by,
                    "request": {"request_id": lt.request_id},
                }
            )
        for po in session.scalars(select(PurchaseOrder)):
            sup = names[po.supplier_id]
            body = (
                f"Purchase order #{po.id} to {sup.name}\nTotal: {po.total_eur:.2f} EUR\n"
                f"Approved by: {po.approved_by}"
                + (f"\nInvoice requested by: {po.invoice_requested_by}" if po.invoice_requested_by else "")
            )
            items.append(
                {
                    "key": f"po:{po.id}",
                    "direction": "out",
                    "kind": "po",
                    "id": po.id,
                    "counterparty": f"{sup.name} <{sup.email}>",
                    "subject": f"Purchase order #{po.id}",
                    "body": body,
                    "at": _iso(po.created_at),
                    "status": po.status,
                    "approved_by": po.approved_by,
                    "request": {"request_id": po.request_id},
                }
            )
    needle = q.strip().lower()
    if needle:
        items = [i for i in items if needle in f"{i['counterparty']} {i['subject']} {i['body']}".lower()]
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items[:limit]


# ---- Analytics --------------------------------------------------------------------------------


def message_analytics(session: Session, days: int = 30) -> dict:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    inbox = list(session.scalars(select(InboxEmail)))
    requests = list(session.scalars(select(CustomerRequest)))
    inbox_ids = {e.message_id for e in inbox}
    parsed_ids = {r.message_id for r in requests}
    inbound = [(e.received_at, e.sender) for e in inbox] + [
        (r.received_at, r.sender) for r in requests if r.message_id not in inbox_ids
    ]
    per_day = Counter(dt.astimezone(UTC).date() for dt, _ in inbound)
    volume = [
        {"day": (start + timedelta(days=i)).isoformat(), "count": per_day.get(start + timedelta(days=i), 0)}
        for i in range(days)
    ]
    rfqs = list(session.scalars(select(Rfq)))
    quotes = list(session.scalars(select(CustomerQuote)))
    pos = list(session.scalars(select(PurchaseOrder)))
    offers = list(session.scalars(select(Offer)))
    outcomes = list(session.scalars(select(Outcome)))
    sent_rfq = [r for r in rfqs if r.status == "sent"]
    sent_quotes = [q for q in quotes if q.status == "sent"]
    confirmed = [r for r in requests if r.status == "confirmed"]
    with_items = Counter()
    for r in requests:
        with_items[len((r.parsed or {}).get("items") or [])] += 1
    confidences = [r.confidence for r in requests if r.model != "manual"]
    return {
        "totals": {
            "inbound": len(inbound),
            "unparsed": len([e for e in inbox if e.message_id not in parsed_ids]),
            "requests": len(requests),
            "outbound_sent": len(sent_rfq) + len(sent_quotes) + len(pos),
            "outbound_drafts": len([r for r in rfqs if r.status == "draft"])
            + len([q for q in quotes if q.status == "draft"]),
        },
        "volume": volume,
        "by_status": dict(Counter(r.status for r in requests)),
        "by_language": dict(Counter((r.parsed or {}).get("language", "?") for r in requests)),
        "by_category": dict(Counter((r.parsed or {}).get("category", "?") for r in requests)),
        "top_senders": [{"sender": s, "count": c} for s, c in Counter(s for _, s in inbound).most_common(8)],
        "avg_confidence": round(statistics.mean(confidences), 3) if confidences else None,
        "funnel": [
            {"stage": "Emails received", "count": len(inbound)},
            {"stage": "Requests created", "count": len(requests)},
            {"stage": "Confirmed by a person", "count": len(confirmed)},
            {"stage": "Supplier RFQs sent", "count": len({r.request_id for r in sent_rfq})},
            {"stage": "Supplier offers received", "count": len({o.request_id for o in offers})},
            {"stage": "Quote sent to customer", "count": len({q.request_id for q in sent_quotes})},
            {
                "stage": "Customer accepted",
                "count": len({o.quote_id for o in outcomes if o.kind == "accepted"}),
            },
            {"stage": "Purchase order", "count": len({p.request_id for p in pos})},
        ],
        "rfq": {
            "sent": len(sent_rfq),
            "answered": len({(o.request_id, o.supplier_id) for o in offers}),
            "demo_simulated": len([o for o in offers if o.source == "demo-simulator"]),
        },
        "outcomes": dict(Counter(o.kind for o in outcomes)),
        "items_per_request": dict(sorted(with_items.items())),
    }


# ---- Suppliers --------------------------------------------------------------------------------

SUPPLIER_FIELDS = (
    "name",
    "country",
    "email",
    "categories",
    "languages",
    "age_years",
    "vat_verified",
    "deals_count",
    "framework_contract",
    "payment_terms_days",
    "warranty_months",
    "sanctioned",
    "flags",
    *profile.PROFILE_FIELDS,
)


def _supplier_dict(s: Supplier) -> dict:
    return {c.name: getattr(s, c.name) for c in s.__table__.columns}


def list_suppliers(session: Session, **filters) -> list[dict]:
    return profile.overview(session, **filters)


def supplier_detail(session: Session, supplier_id: int, settings: Settings) -> dict:
    s = session.get(Supplier, supplier_id)
    if s is None:
        raise LookupError("supplier not found")
    d = _supplier_dict(s)
    today = date.today()
    d["catalog"] = [
        {
            "id": c.id,
            "keyword": c.keyword,
            "description": c.description,
            "unit_price": c.unit_price,
            "currency": c.currency,
            "price_eur": round(to_eur(c.unit_price, c.currency, settings), 4),
            "moq": c.moq,
            "lead_time_days": c.lead_time_days,
            "valid_until": c.valid_until.isoformat(),
            "expired": c.valid_until < today,
            "source": c.source,
        }
        for c in session.scalars(
            select(CatalogPrice).where(CatalogPrice.supplier_id == s.id).order_by(CatalogPrice.keyword)
        )
    ]
    offers = list(session.scalars(select(Offer).where(Offer.supplier_id == s.id)))
    pos = list(session.scalars(select(PurchaseOrder).where(PurchaseOrder.supplier_id == s.id)))
    d["history"] = {
        "rfqs_sent": len(
            list(session.scalars(select(Rfq).where(Rfq.supplier_id == s.id, Rfq.status == "sent")))
        ),
        "offers": len(offers),
        "purchase_orders": len(pos),
        "purchase_total_eur": round(sum(p.total_eur for p in pos), 2),
    }
    d["discounts"] = profile.discounts_of(session, s.id)
    d["checks"] = profile.check_history(session, s.id)
    d["check_result"] = d["checks"][0]["result"] if d["checks"] else "unchecked"
    return d


def create_supplier(session: Session, data: dict, changed_by: str) -> Supplier:
    by = _need_person(changed_by)
    name = data["name"].strip()
    if not name:
        raise ValueError("name is required")
    if session.scalar(select(Supplier).where(Supplier.name == name)):
        raise PipelineError("a supplier with this name already exists")
    country = data["country"].strip().upper()
    if len(country) != 2:
        raise ValueError("country must be a 2-letter code")
    data = profile.clean_profile(data)
    row = Supplier(**{**data, "name": name, "country": country, "flags": data.get("flags") or []})
    session.add(row)
    session.flush()
    _audit(session, by, "supplier.created", supplier_id=row.id, name=name)
    session.commit()
    return row


def update_supplier(session: Session, supplier_id: int, changes: dict, changed_by: str) -> Supplier:
    by = _need_person(changed_by)
    row = session.get(Supplier, supplier_id)
    if row is None:
        raise LookupError("supplier not found")
    changes = profile.clean_profile(changes)
    for key, value in changes.items():
        if key not in SUPPLIER_FIELDS:
            raise ValueError(f"unknown field: {key}")
        if key == "country":
            value = value.strip().upper()
            if len(value) != 2:
                raise ValueError("country must be a 2-letter code")
        setattr(row, key, value)
    _audit(session, by, "supplier.updated", supplier_id=row.id, fields=sorted(changes))
    session.commit()
    return row


def add_catalog_line(session: Session, supplier_id: int, data: dict, changed_by: str) -> CatalogPrice:
    by = _need_person(changed_by)
    if session.get(Supplier, supplier_id) is None:
        raise LookupError("supplier not found")
    if data["currency"] not in ("RSD", "EUR", "USD"):
        raise ValueError("currency must be RSD, EUR or USD")
    if data["unit_price"] <= 0 or data["moq"] < 1:
        raise ValueError("price must be positive and MOQ at least 1")
    row = CatalogPrice(
        supplier_id=supplier_id,
        keyword=data["keyword"].strip().lower(),
        description=data["description"].strip(),
        unit_price=data["unit_price"],
        currency=data["currency"],
        moq=data["moq"],
        lead_time_days=data["lead_time_days"],
        valid_until=data["valid_until"],
        source="manual",
    )
    if not row.keyword:
        raise ValueError("keyword is required")
    session.add(row)
    session.flush()
    _audit(session, by, "catalog.line_added", supplier_id=supplier_id, keyword=row.keyword)
    session.commit()
    return row


# ---- Articles ---------------------------------------------------------------------------------


def _line(c: CatalogPrice, sup: Supplier, settings: Settings, today: date, qty: float | None = None) -> dict:
    eur = to_eur(c.unit_price, c.currency, settings)
    out = {
        "supplier_id": sup.id,
        "supplier": sup.name,
        "country": sup.country,
        "sanctioned": sup.sanctioned,
        "unit_price": c.unit_price,
        "currency": c.currency,
        "price_eur": round(eur, 4),
        "moq": c.moq,
        "lead_time_days": c.lead_time_days,
        "valid_until": c.valid_until.isoformat(),
        "expired": c.valid_until < today,
        "source": c.source,
    }
    if qty is not None:
        out["moq_ok"] = qty >= c.moq
        out["line_total_eur"] = round(eur * qty, 2)
    return out


def _group(
    lines: list[tuple[CatalogPrice, Supplier]], settings: Settings, qty: float | None = None
) -> list[dict]:
    today = date.today()
    groups: dict[str, dict] = {}
    for c, sup in lines:
        g = groups.setdefault(c.keyword, {"keyword": c.keyword, "description": c.description, "lines": []})
        g["lines"].append(_line(c, sup, settings, today, qty))
    out = []
    for g in groups.values():
        usable = [x["price_eur"] for x in g["lines"] if not x["sanctioned"] and not x["expired"]]
        g["lines"].sort(key=lambda x: x["price_eur"])
        g["min_eur"] = min(usable) if usable else None
        g["median_eur"] = round(statistics.median(usable), 4) if usable else None
        g["max_eur"] = max(usable) if usable else None
        g["suppliers"] = len(g["lines"])
        out.append(g)
    out.sort(key=lambda g: g["keyword"])
    return out


def search_articles(session: Session, settings: Settings, q: str = "") -> list[dict]:
    tokens = normalize(q).split()
    suppliers = {s.id: s for s in session.scalars(select(Supplier))}
    rows = []
    for c in session.scalars(select(CatalogPrice)):
        sup = suppliers[c.supplier_id]
        hay = normalize(f"{c.keyword} {c.description} {sup.name}")
        if all(t in hay for t in tokens):
            rows.append((c, sup))
    return _group(rows, settings)


def match_request_items(session: Session, settings: Settings, request_id: int) -> list[dict]:
    get_request(session, request_id)
    suppliers = {s.id: s for s in session.scalars(select(Supplier))}
    out = []
    for item in items_of(session, request_id):
        lines = [(c, suppliers[c.supplier_id]) for c in catalog_lines_for(session, item)]
        out.append(
            {
                "item_id": item.id,
                "description": item.description,
                "part_number": item.part_number,
                "quantity": item.quantity,
                "matches": _group(lines, settings, item.quantity),
            }
        )
    return out


# ---- Quote preview ----------------------------------------------------------------------------


def quote_preview(
    session: Session, settings: Settings, request_id: int, offer_id: int, markup: float, currency: str
) -> dict:
    get_request(session, request_id)
    offer = session.get(Offer, offer_id)
    if offer is None or offer.request_id != request_id:
        raise LookupError("offer not found for this request")
    if markup <= -1:
        raise ValueError("markup must be greater than -100%")
    sup = session.get(Supplier, offer.supplier_id)
    goods_eur = to_eur(offer.total_price, offer.currency, settings)
    cost = landed_cost(goods_eur, sup.country)
    price_eur = cost * (1 + markup)
    return {
        "supplier": sup.name,
        "goods_eur": round(goods_eur, 2),
        "landed_cost_eur": round(cost, 2),
        "price_eur": round(price_eur, 2),
        "price": round(convert(price_eur, "EUR", currency, settings), 2),
        "currency": currency,
        "margin_eur": round(price_eur - cost, 2),
        "below_cost": price_eur < cost,
        "lead_time_days": offer.lead_time_days,
        "excluded": "sanctioned supplier"
        if sup.sanctioned
        else (None if offer.covers_all_items else "offer does not cover all items"),
    }


def public_config(settings: Settings) -> dict:
    return {
        "fx_rsd_per_eur": settings.fx_rsd_per_eur,
        "fx_usd_per_eur": settings.fx_usd_per_eur,
        "default_markup": settings.default_markup,
        "po_budget_limit_eur": settings.po_budget_limit_eur,
        "ai_provider": settings.ai_provider,
        "mail_real_send_enabled": settings.mail_real_send_enabled,
    }


# ---- Price-list import ------------------------------------------------------------------------

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 1_000_000
CSV_COLUMNS = ("keyword", "description", "unit_price", "currency", "moq", "lead_time_days", "valid_until")
_ALIASES = {
    "keyword": ("keyword", "key", "article", "part_number", "part", "sku"),
    "description": ("description", "name", "title"),
    "unit_price": ("unit_price", "price", "unit price"),
    "currency": ("currency", "cur"),
    "moq": ("moq", "min_order", "min_qty"),
    "lead_time_days": ("lead_time_days", "lead_time", "leadtime", "lead time"),
    "valid_until": ("valid_until", "valid_to", "valid until", "expires"),
}


def _number(text: str) -> float:
    return float(text.strip().replace(" ", "").replace(",", "."))


def _cell_reader(raw: list[str], index: dict[str, int]):
    def cell(field: str) -> str:
        return raw[index[field]].strip() if field in index and index[field] < len(raw) else ""

    return cell


def parse_price_csv(text: str, today: date | None = None) -> list[dict]:
    """Validate a price-list CSV. Returns one dict per data row: line, ok, errors, data.
    Nothing is written. Accepts comma, semicolon or tab separators and a decimal comma."""
    import csv
    import io

    today = today or date.today()
    if len(text.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ValueError("file is larger than 1 MB")
    text = text.lstrip("﻿")
    sample = text[:2000]
    delimiter = max(",;\t", key=sample.count) if any(d in sample for d in ",;\t") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        raise ValueError("the file is empty") from None
    index: dict[str, int] = {}
    for field, names in _ALIASES.items():
        for name in names:
            if name in header:
                index[field] = header.index(name)
                break
    missing = [
        f
        for f in ("keyword", "description", "unit_price", "currency", "lead_time_days", "valid_until")
        if f not in index
    ]
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)} (found: {', '.join(header)})")
    rows: list[dict] = []
    for line, raw in enumerate(reader, start=2):
        if not any(c.strip() for c in raw):
            continue
        if len(rows) >= MAX_IMPORT_ROWS:
            raise ValueError(f"more than {MAX_IMPORT_ROWS} rows")
        cell = _cell_reader(raw, index)
        errors: list[str] = []
        data: dict = {"keyword": cell("keyword").lower(), "description": cell("description")}
        if not data["keyword"]:
            errors.append("keyword is empty")
        if not data["description"]:
            errors.append("description is empty")
        try:
            data["unit_price"] = _number(cell("unit_price"))
            if data["unit_price"] <= 0:
                errors.append("price must be positive")
        except ValueError:
            errors.append(f"price is not a number: {cell('unit_price')!r}")
        data["currency"] = cell("currency").upper()
        if data["currency"] not in ("RSD", "EUR", "USD"):
            errors.append(f"currency must be RSD, EUR or USD, got {cell('currency')!r}")
        try:
            data["moq"] = int(_number(cell("moq"))) if cell("moq") else 1
            if data["moq"] < 1:
                errors.append("MOQ must be at least 1")
        except ValueError:
            errors.append(f"MOQ is not a number: {cell('moq')!r}")
        try:
            data["lead_time_days"] = int(_number(cell("lead_time_days")))
            if data["lead_time_days"] < 0:
                errors.append("lead time cannot be negative")
        except ValueError:
            errors.append(f"lead time is not a number: {cell('lead_time_days')!r}")
        try:
            data["valid_until"] = date.fromisoformat(cell("valid_until"))
            if data["valid_until"] < today:
                errors.append(f"already expired ({data['valid_until']})")
        except ValueError:
            errors.append(f"valid_until must be YYYY-MM-DD, got {cell('valid_until')!r}")
        rows.append({"line": line, "ok": not errors, "errors": errors, "data": data})
    if not rows:
        raise ValueError("no data rows found")
    seen: dict[str, int] = {}
    for r in rows:
        key = r["data"]["keyword"]
        if key in seen and r["ok"]:
            r["ok"] = False
            r["errors"].append(f"duplicate keyword, first seen on line {seen[key]}")
        elif key:
            seen.setdefault(key, r["line"])
    return rows


def import_price_list(
    session: Session, supplier_id: int, text: str, changed_by: str, dry_run: bool = True
) -> dict:
    """Validate a CSV and, unless dry_run, apply it atomically: if any row is invalid nothing is
    written. A row whose keyword the supplier already has updates that line (price refresh)."""
    by = _need_person(changed_by)
    if session.get(Supplier, supplier_id) is None:
        raise LookupError("supplier not found")
    rows = parse_price_csv(text)
    errors = [r for r in rows if not r["ok"]]
    existing = {
        c.keyword: c
        for c in session.scalars(select(CatalogPrice).where(CatalogPrice.supplier_id == supplier_id))
    }
    for r in rows:
        r["action"] = "update" if r["data"]["keyword"] in existing else "add"
        r["data"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in r["data"].items()}
    result = {
        "rows": rows,
        "total": len(rows),
        "invalid": len(errors),
        "to_add": sum(1 for r in rows if r["ok"] and r["action"] == "add"),
        "to_update": sum(1 for r in rows if r["ok"] and r["action"] == "update"),
        "applied": False,
    }
    if dry_run:
        return result
    if errors:
        raise PipelineError(f"{len(errors)} row(s) are invalid; fix the file, nothing was imported")
    for r in rows:
        d = r["data"]
        valid_until = date.fromisoformat(d["valid_until"])
        line = existing.get(d["keyword"])
        if line is None:
            session.add(
                CatalogPrice(
                    supplier_id=supplier_id,
                    source="csv-import",
                    valid_until=valid_until,
                    **{k: v for k, v in d.items() if k != "valid_until"},
                )
            )
        else:
            for k, v in d.items():
                setattr(line, k, valid_until if k == "valid_until" else v)
            line.source = "csv-import"
    _audit(
        session,
        by,
        "catalog.csv_imported",
        supplier_id=supplier_id,
        added=result["to_add"],
        updated=result["to_update"],
    )
    session.commit()
    result["applied"] = True
    return result


# ---- Approval queue ---------------------------------------------------------------------------


def approvals(session: Session, settings: Settings, status: str = "pending", limit: int = 100) -> list[dict]:
    """Every outgoing letter that waits for (or went through) a person's decision, newest first."""
    pending = status == "pending"
    want = ("draft",) if pending else ("sent", "rejected")
    suppliers = {s.id: s for s in session.scalars(select(Supplier))}
    items: list[dict] = []
    for r in session.scalars(select(Rfq).where(Rfq.status.in_(want))):
        sup = suppliers[r.supplier_id]
        items.append(
            {
                "key": f"rfq:{r.id}",
                "kind": "rfq",
                "id": r.id,
                "request_id": r.request_id,
                "counterparty": f"{sup.name} <{sup.email}>",
                "subject": r.subject,
                "body": r.body,
                "language": r.language,
                "status": r.status,
                "decided_by": r.decided_by,
                "at": _iso(r.created_at),
                "warnings": ["supplier is marked sanctioned"] if sup.sanctioned else [],
                "drafted_by": r.drafted_by,
            }
        )
    for lt in session.scalars(select(Letter).where(Letter.status.in_(want))):
        sup = suppliers.get(lt.supplier_id) if lt.supplier_id else None
        items.append(
            {
                "key": f"letter:{lt.id}",
                "kind": lt.kind,
                "id": lt.id,
                "request_id": lt.request_id,
                "counterparty": f"{sup.name} <{sup.email}>" if sup else lt.to_email,
                "subject": lt.subject,
                "body": lt.body,
                "language": lt.language,
                "status": lt.status,
                "decided_by": lt.decided_by,
                "at": _iso(lt.created_at),
                "warnings": ["supplier is marked sanctioned"] if sup and sup.sanctioned else [],
                "drafted_by": lt.drafted_by,
                "reason": lt.reason,
            }
        )
    for q in session.scalars(select(CustomerQuote).where(CustomerQuote.status.in_(want))):
        req = session.get(CustomerRequest, q.request_id)
        price_eur = to_eur(q.price, q.currency, settings)
        warnings = ["price is below cost"] if price_eur < q.cost_eur else []
        items.append(
            {
                "key": f"quote:{q.id}",
                "kind": "quote",
                "id": q.id,
                "request_id": q.request_id,
                "counterparty": req.sender if req else "",
                "subject": q.subject,
                "body": q.body,
                "language": q.language,
                "status": q.status,
                "decided_by": q.decided_by,
                "at": _iso(q.created_at),
                "warnings": warnings,
                "drafted_by": q.drafted_by,
                "quote": {
                    "price": q.price,
                    "currency": q.currency,
                    "cost_eur": q.cost_eur,
                    "markup": q.markup,
                },
            }
        )
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items[:limit]
