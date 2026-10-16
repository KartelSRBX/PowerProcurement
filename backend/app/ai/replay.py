"""Recorded-response adapters. CI and the public demo never call the live API.

Recording key = sha256(prompt id, prompt version, rendered text). Change the prompt
or the input and the key changes, so a stale recording can never silently answer.
"""

import hashlib
import json
from pathlib import Path

from app.ai.base import AIAdapter, AIResult, T
from app.ai.prompts import PromptTemplate


class RecordingNotFound(LookupError):
    pass


def recording_key(prompt: PromptTemplate, variables: dict[str, str]) -> str:
    raw = f"{prompt.id}\n{prompt.version}\n{prompt.render(variables)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class ReplayAdapter:
    def __init__(self, directory: Path, model: str = "recorded"):
        self.directory = directory
        self.model = model

    def extract(self, prompt: PromptTemplate, variables: dict[str, str], schema: type[T]) -> AIResult[T]:
        path = self.directory / f"{prompt.id}.{prompt.version}.{recording_key(prompt, variables)}.json"
        if not path.is_file():
            raise RecordingNotFound(f"no recording at {path.name}; record it with a live run")
        data = json.loads(path.read_text(encoding="utf-8"))
        return AIResult(
            parsed=schema.model_validate(data["answer"]),
            model=data.get("model", self.model),
            prompt_id=prompt.id,
            prompt_version=prompt.version,
        )


class RecordingAdapter:
    """Wraps a live adapter and saves each answer so it can be replayed later."""

    def __init__(self, inner: AIAdapter, directory: Path):
        self.inner = inner
        self.directory = directory

    def extract(self, prompt: PromptTemplate, variables: dict[str, str], schema: type[T]) -> AIResult[T]:
        result = self.inner.extract(prompt, variables, schema)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{prompt.id}.{prompt.version}.{recording_key(prompt, variables)}.json"
        path.write_text(
            json.dumps({"model": result.model, "answer": result.parsed.model_dump()}, indent=2),
            encoding="utf-8",
        )
        return result
