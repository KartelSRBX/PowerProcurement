from typing import Literal

from pydantic import BaseModel

from app.ai.base import Confident


class AIFinding(BaseModel):
    title: str
    quote: str
    severity: Literal["red", "yellow", "info"]
    risk: str
    suggest: str


class ContractReview(Confident):
    findings: list[AIFinding] = []
