"""What the model returns for each assisted step. Text and extracted facts only; no decisions."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.ai.base import Confident

Currency = Literal["EUR", "RSD", "USD", "other"]


class SupplierSuggestion(BaseModel):
    supplier_id: int
    items: list[int]  # 1-based item numbers the supplier is likely to sell
    reason: str


class SupplierWhy(BaseModel):
    supplier_id: int
    reason: str


class SupplierPool(Confident):
    suggestions: list[SupplierSuggestion] = []
    explanations: list[SupplierWhy] = []


class LetterDraft(Confident):
    subject: str
    body: str


class ReplyLine(BaseModel):
    item: int  # 1-based item number from the request
    unit_price: float | None = None
    currency: Currency | None = None
    offered_quantity: float | None = None
    lead_time_days: int | None = None
    moq: float | None = None
    note: str | None = None


class SupplierReply(Confident):
    is_offer: bool  # false for "we will answer later", out-of-office, refusals
    lines: list[ReplyLine] = []
    stated_total: float | None = None  # only when the supplier writes an overall total
    stated_currency: Currency | None = None
    lead_time_days: int | None = None  # one lead time for the whole order, if that is how it is given
    valid_until: date | None = None
    payment_terms: str | None = None
    warranty: str | None = None
    notes: str = ""
    missing: list[str] = []  # facts we asked for and the answer does not give
    problems: list[str] = []  # anything unusual: substitutes, partial coverage, conditions


class CustomerAnswer(Confident):
    kind: Literal["accepted", "counter", "rejected", "silence", "unclear"]
    price: float | None = None
    currency: Literal["EUR", "RSD", "USD"] | None = None
    reason: str | None = None


class SupplierExplanation(BaseModel):
    offer_id: int
    text: str


class ScoreExplanation(Confident):
    summary: str
    suppliers: list[SupplierExplanation] = []


class Narrative(Confident):
    headline: str
    points: list[str] = []
