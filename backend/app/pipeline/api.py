from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.currency import to_eur
from app.db import get_session
from app.intake.schemas import ParsedRequest
from app.mail.sender import MailSender, SendRefused
from app.models import (
    CustomerQuote,
    MarketPrice,
    Offer,
    Outcome,
    PriceEvent,
    PurchaseOrder,
    RequestItem,
    Rfq,
    ShortlistEntry,
    Supplier,
)
from app.pipeline import compare
from app.pipeline import service as svc
from app.scoring.scoring import Weights

router = APIRouter(tags=["pipeline"])


def get_sender(settings: Settings = Depends(get_settings)) -> MailSender:
    return MailSender(settings)


def guarded(fn, *args, **kwargs):
    """Map domain errors to HTTP codes in one place."""
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except svc.PipelineError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SendRefused as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _dump(row, *skip: str) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in skip}


# ---- payloads ---------------------------------------------------------------------------------


class ManualRequestIn(BaseModel):
    sender: str
    subject: str
    body: str = ""
    parsed: ParsedRequest
    confirmed_by: str
    message_id: str | None = None


class SelectIn(BaseModel):
    selected: bool


class RfqEditIn(BaseModel):
    subject: str | None = None
    body: str | None = None


class DecisionIn(BaseModel):
    approve: bool
    decided_by: str


class LineIn(BaseModel):
    item_id: int
    unit_price: float
    moq: float | None = None


class OfferIn(BaseModel):
    supplier_id: int
    total_price: float
    currency: str
    lead_time_days: int
    covers_all_items: bool = True
    moq_ok: bool = True
    valid_until: date | None = None
    incoterm: str | None = None
    incoterm_place: str | None = None
    payment_days: int | None = None
    lines: list[LineIn] | None = None


class WeightsIn(BaseModel):
    price: int = 30
    lead_time: int = 20
    reliability: int = 20
    terms: int = 15
    external_risk: int = 15


class QuoteIn(BaseModel):
    offer_id: int
    markup: float | None = None
    currency: str = "EUR"
    created_by: str


class OutcomeIn(BaseModel):
    kind: str
    price: float | None = None
    currency: str | None = None
    reason: str | None = None
    confirmed_by: str


class ApprovalIn(BaseModel):
    approved_by: str


class InvoiceIn(BaseModel):
    approved_by: str
    subject: str | None = None
    body: str | None = None


# ---- routes ---------------------------------------------------------------------------------------


@router.post("/requests/manual")
def manual_request(body: ManualRequestIn, session: Session = Depends(get_session)):
    row = guarded(
        svc.create_manual_request,
        session,
        body.sender,
        body.subject,
        body.body,
        body.parsed,
        body.confirmed_by,
        body.message_id,
    )
    return {"id": row.id, "status": row.status}


@router.get("/requests/{request_id}/pipeline")
def pipeline(request_id: int, session: Session = Depends(get_session)):
    return guarded(svc.stage_of, session, request_id)


@router.get("/requests/{request_id}/items")
def items(request_id: int, session: Session = Depends(get_session)):
    return [_dump(i) for i in svc.items_of(session, request_id)]


@router.post("/requests/{request_id}/discover")
def discover(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(svc.run_discovery, session, settings, request_id)


@router.get("/requests/{request_id}/shortlist")
def shortlist(request_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(
        select(ShortlistEntry).where(ShortlistEntry.request_id == request_id).order_by(ShortlistEntry.rank)
    )
    out = []
    for e in rows:
        sup = session.get(Supplier, e.supplier_id)
        out.append({**_dump(e), "supplier": sup.name, "country": sup.country})
    return out


@router.post("/requests/{request_id}/shortlist/{supplier_id}")
def select_supplier(
    request_id: int, supplier_id: int, body: SelectIn, session: Session = Depends(get_session)
):
    guarded(svc.set_supplier_selected, session, request_id, supplier_id, body.selected)
    return {"ok": True}


@router.get("/requests/{request_id}/market-prices")
def market_prices(request_id: int, session: Session = Depends(get_session)):
    rows = session.execute(
        select(MarketPrice, RequestItem)
        .join(RequestItem, MarketPrice.request_item_id == RequestItem.id)
        .where(RequestItem.request_id == request_id)
    ).all()
    return [{**_dump(m), "item": i.description, "label": "unconfirmed (demo catalog)"} for m, i in rows]


@router.post("/requests/{request_id}/rfqs/draft")
def draft(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    guarded(svc.draft_rfqs, session, settings, request_id)
    return list_rfqs(request_id, session)


@router.get("/requests/{request_id}/rfqs")
def list_rfqs(request_id: int, session: Session = Depends(get_session)):
    out = []
    for r in session.scalars(select(Rfq).where(Rfq.request_id == request_id).order_by(Rfq.id)):
        out.append({**_dump(r), "supplier": session.get(Supplier, r.supplier_id).name})
    return out


@router.patch("/rfqs/{rfq_id}")
def edit_rfq(rfq_id: int, body: RfqEditIn, session: Session = Depends(get_session)):
    return _dump(guarded(svc.edit_rfq, session, rfq_id, body.subject, body.body))


@router.post("/rfqs/{rfq_id}/decision")
def decide_rfq(
    rfq_id: int,
    body: DecisionIn,
    session: Session = Depends(get_session),
    sender: MailSender = Depends(get_sender),
):
    return _dump(guarded(svc.decide_rfq, session, sender, rfq_id, body.approve, body.decided_by))


@router.post("/requests/{request_id}/offers")
def add_offer(
    request_id: int,
    body: OfferIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return _dump(guarded(svc.add_offer, session, settings, request_id, **body.model_dump()))


@router.post("/requests/{request_id}/offers/simulate")
def simulate(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return [_dump(o) for o in guarded(svc.simulate_offers, session, settings, request_id)]


@router.get("/requests/{request_id}/offers")
def offers(request_id: int, session: Session = Depends(get_session)):
    return [_dump(o) for o in session.scalars(select(Offer).where(Offer.request_id == request_id))]


@router.get("/requests/{request_id}/comparison")
def comparison(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(compare.compare_offers, session, settings, request_id)


@router.get("/requests/{request_id}/comparison.xlsx")
def comparison_xlsx(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    data = guarded(compare.comparison_xlsx, session, settings, request_id)
    return Response(
        data,
        media_type=compare.XLSX,
        headers={"content-disposition": f'attachment; filename="request-{request_id}-comparison.xlsx"'},
    )


@router.post("/requests/{request_id}/score")
def score(
    request_id: int,
    body: WeightsIn | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    w = Weights(**(body.model_dump() if body else {}))
    return guarded(svc.score_request, session, settings, request_id, w)


@router.post("/requests/{request_id}/quotes")
def create_quote(
    request_id: int,
    body: QuoteIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return _dump(
        guarded(
            svc.create_quote,
            session,
            settings,
            request_id,
            body.offer_id,
            body.markup,
            body.currency,
            body.created_by,
        )
    )


@router.get("/requests/{request_id}/quotes")
def quotes(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return [
        _dump(q) | {"price_eur": round(to_eur(q.price, q.currency, settings), 2)}
        for q in session.scalars(select(CustomerQuote).where(CustomerQuote.request_id == request_id))
    ]


@router.patch("/quotes/{quote_id}")
def edit_quote(quote_id: int, body: RfqEditIn, session: Session = Depends(get_session)):
    q = session.get(CustomerQuote, quote_id)
    if q is None:
        raise HTTPException(404, "quote not found")
    if q.status != "draft":
        raise HTTPException(409, "only drafts can be edited")
    q.subject, q.body = body.subject or q.subject, body.body or q.body
    session.commit()
    return _dump(q)


@router.post("/quotes/{quote_id}/decision")
def decide_quote(
    quote_id: int,
    body: DecisionIn,
    session: Session = Depends(get_session),
    sender: MailSender = Depends(get_sender),
):
    return _dump(guarded(svc.decide_quote, session, sender, quote_id, body.approve, body.decided_by))


@router.post("/quotes/{quote_id}/outcome")
def outcome(quote_id: int, body: OutcomeIn, session: Session = Depends(get_session)):
    return _dump(
        guarded(
            svc.record_outcome,
            session,
            quote_id,
            body.kind,
            body.price,
            body.currency,
            body.reason,
            body.confirmed_by,
        )
    )


@router.post("/requests/{request_id}/orders")
def order(
    request_id: int,
    body: ApprovalIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    sender: MailSender = Depends(get_sender),
):
    return _dump(guarded(svc.create_po, session, sender, settings, request_id, body.approved_by))


@router.post("/orders/{po_id}/invoice-request")
def invoice(
    po_id: int,
    body: InvoiceIn,
    session: Session = Depends(get_session),
    sender: MailSender = Depends(get_sender),
    settings: Settings = Depends(get_settings),
):
    return _dump(
        guarded(
            svc.request_invoice, session, sender, po_id, body.approved_by, settings, body.subject, body.body
        )
    )


@router.get("/orders/{po_id}/invoice-draft")
def invoice_draft(
    po_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(svc.invoice_draft, session, settings, po_id)


@router.get("/requests/{request_id}/price-events")
def price_events(request_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(
        select(PriceEvent).where(PriceEvent.request_id == request_id).order_by(PriceEvent.id)
    )
    return [_dump(p) for p in rows]


@router.get("/requests/{request_id}/orders")
def list_orders(request_id: int, session: Session = Depends(get_session)):
    return [
        _dump(p) for p in session.scalars(select(PurchaseOrder).where(PurchaseOrder.request_id == request_id))
    ]


@router.get("/requests/{request_id}/outcomes")
def list_outcomes(request_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Outcome)
        .join(CustomerQuote, Outcome.quote_id == CustomerQuote.id)
        .where(CustomerQuote.request_id == request_id)
    )
    return [_dump(o) for o in rows]


@router.get("/suppliers")
def suppliers(session: Session = Depends(get_session)):
    return [_dump(s) for s in session.scalars(select(Supplier).order_by(Supplier.name))]
