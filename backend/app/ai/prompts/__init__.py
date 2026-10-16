"""Versioned prompt files: prompts/<id>/<version>.md. A prompt is never edited in place;
a change is a new version, so recorded responses and eval results stay attributable."""

from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent


@dataclass(frozen=True)
class PromptTemplate:
    id: str
    version: str
    text: str

    def render(self, variables: dict[str, str]) -> str:
        return Template(self.text).substitute(variables)


def load_prompt(prompt_id: str, version: str) -> PromptTemplate:
    path = PROMPTS_DIR / prompt_id / f"{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt {prompt_id}/{version} not found at {path}")
    return PromptTemplate(prompt_id, version, path.read_text(encoding="utf-8"))
