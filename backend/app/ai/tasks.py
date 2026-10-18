"""Optional AI steps. Every caller works without them: when AI is off, or a call fails, or the answer
is below the confidence threshold, the caller gets None plus a plain note and uses its template or rule.
The model only reads and writes text here; numbers and actions stay in code."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.ai import load_prompt, make_adapter
from app.ai.base import AIAdapter, AIResult, T
from app.config import Settings
from app.models import AuditLog

AdapterFactory = Callable[[Settings], AIAdapter]
_factory: AdapterFactory = make_adapter


def set_adapter_factory(factory: AdapterFactory | None) -> None:
    """Tests inject a fake model here; None restores the real one."""
    global _factory
    _factory = factory or make_adapter


def ai_enabled(settings: Settings) -> bool:
    return settings.ai_provider == "anthropic" and bool(settings.anthropic_api_key)


def run_task(
    session: Session,
    settings: Settings,
    prompt_id: str,
    variables: dict[str, str],
    schema: type[T],
    version: str = "v1",
) -> tuple[AIResult[T] | None, str | None]:
    """Returns (result, note). (None, None): AI is off. (None, note): the call failed or was too
    unsure; note says why and the caller falls back. Never raises for model or network trouble."""
    if not ai_enabled(settings):
        return None, None
    try:
        result = _factory(settings).extract(load_prompt(prompt_id, version), variables, schema)
    except Exception as exc:  # noqa: BLE001 - any model or network failure must fall back, not break the step
        reason = f"{type(exc).__name__}: {str(exc)[:200]}"
        session.add(
            AuditLog(actor="system", action="ai.failed", payload={"prompt": prompt_id, "error": reason})
        )
        session.commit()
        return None, f"AI call failed ({type(exc).__name__}); the template was used instead"
    if result.parsed.confidence < settings.ai_confidence_threshold:
        return None, (
            f"AI was not sure enough ({result.parsed.confidence:.0%} confidence, "
            f"limit {settings.ai_confidence_threshold:.0%}); the template was used instead"
        )
    return result, None
