from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.crm import service as svc
from app.db import get_session
from app.pipeline.api import guarded
from app.suppliers import articles as articles_notes
from app.suppliers import profile

router = APIRouter(tags=["crm"])


@router.get("/config")
def config(settings: Settings = Depends(get_settings)):
    return svc.public_config(settings)


# ---- mail -------------------------------------------------------------------------------------


@router.get("/mail")
def mail(folder: str = "all", q: str = "", session: Session = Depends(get_session)):
    return svc.mail_feed(session, folder, q)


class AttachIn(BaseModel):
    request_id: int
    supplier_id: int
    by: str


class ByIn(BaseModel):
    by: str


@router.get("/mail/unattached")
def unattached(session: Session = Depends(get_session)):
    return svc.unattached_mail(session)


@router.post("/mail/{email_id}/attach")
def attach(email_id: int, body: AttachIn, session: Session = Depends(get_session)):
    row = guarded(svc.attach_mail, session, email_id, body.request_id, body.supplier_id, body.by)
    return {"id": row.id, "route": row.route, "request_id": row.route_request_id}


@router.post("/mail/{email_id}/not-supplier")
def not_supplier(email_id: int, body: ByIn, session: Session = Depends(get_session)):
    row = guarded(svc.mark_not_supplier, session, email_id, body.by)
    return {"id": row.id, "route": row.route}


@router.post("/mail/demo-load")
def demo_load(session: Session = Depends(get_session)):
    return {"added": svc.load_demo_inbox(session)}


@router.get("/approvals")
def approvals(
    status: str = "pending",
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return svc.approvals(session, settings, "pending" if status == "pending" else "decided")


# ---- analytics --------------------------------------------------------------------------------


@router.get("/analytics/messages")
def analytics(days: int = 30, session: Session = Depends(get_session)):
    return svc.message_analytics(session, max(1, min(days, 180)))


# ---- suppliers --------------------------------------------------------------------------------


class SupplierIn(BaseModel):
    name: str
    country: str
    email: str
    categories: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    age_years: int = 0
    vat_verified: bool = False
    deals_count: int = 0
    framework_contract: bool = False
    payment_terms_days: int = 0
    warranty_months: int = 0
    sanctioned: bool = False
    brands: list[str] = Field(default_factory=list)
    product_types: list[str] = Field(default_factory=list)
    brand_tiers: dict[str, str] = Field(default_factory=dict)
    changed_by: str


class SupplierPatch(BaseModel):
    changes: dict[str, Any]
    changed_by: str


class CatalogLineIn(BaseModel):
    keyword: str
    description: str
    unit_price: float
    currency: str
    moq: int = 1
    lead_time_days: int
    valid_until: date
    changed_by: str


class CatalogImportIn(BaseModel):
    csv: str
    changed_by: str
    dry_run: bool = True


@router.get("/suppliers/overview")
def suppliers_overview(
    q: str = "",
    country: str = "",
    category: str = "",
    brand: str = "",
    tier: str = "",
    check: str = "",
    status: str = "",
    sort: str = "name",
    dir: str = "asc",
    session: Session = Depends(get_session),
):
    return guarded(
        svc.list_suppliers,
        session,
        q=q,
        country=country,
        category=category,
        brand=brand,
        tier=tier,
        check=check,
        status=status,
        sort=sort,
        direction=dir,
    )


@router.get("/suppliers/facets")
def suppliers_facets(country: str = "", category: str = "", session: Session = Depends(get_session)):
    return profile.facets(session, country, category)


@router.get("/suppliers/checks")
def supplier_checks(result: str = "", session: Session = Depends(get_session)):
    return profile.checks_overview(session, result)


class CheckIn(BaseModel):
    result: str
    checked_by: str
    contact_details: str | None = None
    note: str | None = None


class DiscountIn(BaseModel):
    brand: str
    description: str
    changed_by: str


class WhoIn(BaseModel):
    changed_by: str


@router.post("/suppliers/{supplier_id}/checks")
def add_check(supplier_id: int, body: CheckIn, session: Session = Depends(get_session)):
    row = guarded(
        profile.add_check,
        session,
        supplier_id,
        body.result,
        body.checked_by,
        body.contact_details,
        body.note,
    )
    return profile.check_dict(row)


@router.post("/suppliers/{supplier_id}/discounts")
def add_discount(supplier_id: int, body: DiscountIn, session: Session = Depends(get_session)):
    row = guarded(profile.add_discount, session, supplier_id, body.brand, body.description, body.changed_by)
    return {"id": row.id, "brand": row.brand, "description": row.description}


@router.delete("/suppliers/discounts/{discount_id}")
def remove_discount(discount_id: int, changed_by: str, session: Session = Depends(get_session)):
    guarded(profile.remove_discount, session, discount_id, changed_by)
    return {"ok": True}


@router.get("/suppliers/{supplier_id}")
def supplier(
    supplier_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(svc.supplier_detail, session, supplier_id, settings)


@router.post("/suppliers")
def create_supplier(body: SupplierIn, session: Session = Depends(get_session)):
    data = body.model_dump(exclude={"changed_by"})
    row = guarded(svc.create_supplier, session, data, body.changed_by)
    return {"id": row.id}


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierPatch, session: Session = Depends(get_session)):
    row = guarded(svc.update_supplier, session, supplier_id, body.changes, body.changed_by)
    return {"id": row.id}


@router.post("/suppliers/{supplier_id}/catalog")
def add_catalog_line(supplier_id: int, body: CatalogLineIn, session: Session = Depends(get_session)):
    row = guarded(
        svc.add_catalog_line, session, supplier_id, body.model_dump(exclude={"changed_by"}), body.changed_by
    )
    return {"id": row.id}


@router.post("/suppliers/{supplier_id}/catalog/import")
def import_catalog(supplier_id: int, body: CatalogImportIn, session: Session = Depends(get_session)):
    return guarded(svc.import_price_list, session, supplier_id, body.csv, body.changed_by, body.dry_run)


# ---- articles and quote preview ---------------------------------------------------------------


@router.get("/articles/search")
def articles(
    q: str = "", session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return svc.search_articles(session, settings, q)


class ArticleRecordIn(BaseModel):
    set_by: str
    part_number: str | None = None
    description: str | None = None
    brand: str | None = None
    eol: bool = False
    eol_since: date | None = None
    eol_note: str = Field(default="", max_length=300)


class ArticleAlternateIn(BaseModel):
    set_by: str
    part_number: str | None = None
    description: str | None = None
    alt_part_number: str | None = None
    alt_description: str | None = None
    kind: str
    note: str = Field(default="", max_length=300)


@router.get("/articles/notes")
def article_notes(q: str = "", session: Session = Depends(get_session)):
    return articles_notes.listing(session, q)


@router.put("/articles/notes")
def set_article_note(body: ArticleRecordIn, session: Session = Depends(get_session)):
    return guarded(articles_notes.set_record, session, **body.model_dump())


@router.delete("/articles/notes/{record_id}")
def remove_article_note(record_id: int, removed_by: str, session: Session = Depends(get_session)):
    guarded(articles_notes.remove_record, session, record_id, removed_by)
    return articles_notes.listing(session)


@router.post("/articles/alternates")
def add_article_alternate(body: ArticleAlternateIn, session: Session = Depends(get_session)):
    return guarded(articles_notes.add_alternate, session, **body.model_dump())


@router.delete("/articles/alternates/{alt_id}")
def remove_article_alternate(alt_id: int, removed_by: str, session: Session = Depends(get_session)):
    guarded(articles_notes.remove_alternate, session, alt_id, removed_by)
    return articles_notes.listing(session)


@router.get("/requests/{request_id}/articles")
def request_articles(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(svc.match_request_items, session, settings, request_id)


@router.get("/requests/{request_id}/quote-preview")
def quote_preview(
    request_id: int,
    offer_id: int,
    markup: float,
    currency: str = "EUR",
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(svc.quote_preview, session, settings, request_id, offer_id, markup, currency)
