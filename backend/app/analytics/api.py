from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics import pricing
from app.analytics.synthetic import load_synthetic
from app.config import Settings, get_settings
from app.db import get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/pricing")
def pricing_overview(
    customer: str | None = None,
    category: str | None = None,
    source: str = "all",
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    rows = pricing.load_rows(session, settings, source)
    return pricing.overview(rows, customer or None, category or None)


@router.get("/markup-suggestion")
def markup_suggestion(
    customer: str | None = None,
    category: str | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    rows = pricing.load_rows(session, settings)
    return pricing.suggestion(rows, customer or None, category or None)


@router.post("/demo-history")
def demo_history(session: Session = Depends(get_session)):
    return {"added": load_synthetic(session)}
