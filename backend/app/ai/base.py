"""Single interface for every model call in the system.

Rules this module enforces by construction:
- every answer is structured (a pydantic schema), never free text;
- every answer carries a confidence score;
- below the configured threshold the caller must route the item to a human.
The model extracts and explains. It never decides numbers or actions.
"""

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

from app.ai.prompts import PromptTemplate


class Confident(BaseModel):
    """Base class for all AI answer schemas."""

    confidence: float = Field(ge=0, le=1, description="Model's own confidence in this answer.")


T = TypeVar("T", bound=Confident)


@dataclass(frozen=True)
class AIResult[T: Confident]:
    parsed: T
    model: str
    prompt_id: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0


class AIAdapter(Protocol):
    def extract(self, prompt: PromptTemplate, variables: dict[str, str], schema: type[T]) -> AIResult[T]: ...


def needs_human(result: AIResult, threshold: float) -> bool:
    """True when the answer is too uncertain to continue without a person."""
    return result.parsed.confidence < threshold
