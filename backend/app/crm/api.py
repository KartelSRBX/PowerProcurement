from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.crm import service as svc
from app.db import get_session
from app.pipeline.api import guarded

router = APIRouter(tags=["crm"])


@router.get("/config")
def config(settings: Settings = Depends(get_settings)):
    return svc.public_config(settings)


# ---- mail -------------------------------------------------------------------------------------


@router.get("/mail")
def mail(folder: str = "all", q: str = "", session: Session = Depends(get_session)):
    return svc.mail_feed(session, folder, q)


@router.post("/mail/demo-load")
def demo_load(session: Session = Depends(get_session)):
    return {"added": svc.load_demo_inbox(session)}


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
def suppliers_overview(session: Session = Depends(get_session)):
    return svc.list_suppliers(session)


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
