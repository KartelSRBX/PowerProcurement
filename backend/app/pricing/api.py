from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.pricing import calculator as calc

router = APIRouter(tags=["landed-cost"])

Money = Field(default=None, ge=0, le=1e12)
Pct = Field(default=None, ge=0, le=1000)


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    quantity: float = Field(gt=0, le=1e12)
    unit_price: float = Field(gt=0, le=1e12)
    hs_code: str | None = Field(default=None, max_length=20)
    duty_pct: float | None = Pct
    vat_pct: float | None = Pct


class LandedIn(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    incoterm: str | None = Field(default=None, max_length=3)
    lines: list[LineIn] = Field(min_length=1, max_length=200)
    origin: float | None = Money
    freight: float | None = Money
    insurance: float | None = Money
    insurance_pct: float | None = Pct
    inland: float | None = Money
    clearance: float | None = Money
    inland_in_price: float = Field(default=0.0, ge=0, le=1e12)
    vat_pct: float | None = Pct
    vat_recoverable: bool = True


@router.post("/pricing/landed")
def landed(
    body: LandedIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    data = body.model_dump()
    lines = [calc.CalcLine(**ln) for ln in data.pop("lines")]
    try:
        inp = calc.CalcInput(lines=lines, **data)
        return calc.check_rates(session, settings, inp, calc.calculate(inp, settings))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class SaveIn(LandedIn):
    saved_by: str = Field(max_length=128)


@router.put("/offers/{offer_id}/cost")
def save_cost(
    offer_id: int,
    body: SaveIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    inputs = body.model_dump(exclude={"saved_by"})
    try:
        return calc.save_for_offer(session, settings, offer_id, inputs, body.saved_by)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/offers/{offer_id}/cost")
def delete_cost(offer_id: int, session: Session = Depends(get_session)):
    try:
        calc.delete_for_offer(session, offer_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": True}


@router.get("/requests/{request_id}/landed-draft")
def draft(
    request_id: int,
    offer_id: int | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return calc.draft_from_request(session, settings, request_id, offer_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
