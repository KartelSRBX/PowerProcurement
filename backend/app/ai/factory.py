from pathlib import Path

from app.ai.anthropic_adapter import AnthropicAdapter
from app.ai.base import AIAdapter
from app.ai.replay import ReplayAdapter
from app.config import Settings

RECORDINGS_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_recordings"


def make_adapter(settings: Settings) -> AIAdapter:
    if settings.ai_provider == "anthropic":
        return AnthropicAdapter(settings.anthropic_api_key, settings.ai_model, settings.ai_max_tokens)
    return ReplayAdapter(RECORDINGS_DIR)
