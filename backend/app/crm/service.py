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
    Offer,
    Outcome,
    PurchaseOrder,
    Rfq,
    Supplier,
)
from app.pipeline.service import PipelineError, get_request, items_of
from app.scoring.scoring import landed_cost
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
)


def _supplier_dict(s: Supplier) -> dict:
    return {c.name: getattr(s, c.name) for c in s.__table__.columns}


def list_suppliers(session: Session) -> list[dict]:
    lines = Counter(c.supplier_id for c in session.scalars(select(CatalogPrice)))
    offers = Counter(o.supplier_id for o in session.scalars(select(Offer)))
    out = []
    for s in session.scalars(select(Supplier).order_by(Supplier.name)):
        d = _supplier_dict(s)
        d["catalog_lines"] = lines.get(s.id, 0)
        d["offers"] = offers.get(s.id, 0)
        out.append(d)
    return out


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
