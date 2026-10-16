"""What the model returns for one incoming email. Everything here is data the model
extracts or states; none of it is a decision. Money and dates are kept as extracted."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.ai.base import Confident

Language = Literal["sr", "en", "other"]
Category = Literal["electronics", "it_hardware", "other"]
Currency = Literal["RSD", "EUR", "USD"]


class RequestItem(BaseModel):
    description: str
    quantity: float | None = None
    unit: str | None = None
    part_number: str | None = None


class ParsedRequest(Confident):
    is_request: bool
    language: Language
    customer_name: str | None = None
    category: Category
    items: list[RequestItem]
    budget_amount: float | None = None
    budget_currency: Currency | None = None
    needed_by: date | None = None
    delivery_country: str | None = None
    questions: list[str] = []
