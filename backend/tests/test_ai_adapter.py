from types import SimpleNamespace

import pytest

from app.ai import Confident, load_prompt, needs_human
from app.ai.anthropic_adapter import AnthropicAdapter
from app.ai.base import AIResult
from app.ai.replay import RecordingAdapter, RecordingNotFound, ReplayAdapter


class Echo(Confident):
    word: str


class FakeLive:
    def extract(self, prompt, variables, schema):
        return AIResult(schema(word=variables["word"], confidence=0.9), "fake", prompt.id, prompt.version)


def test_prompt_is_loaded_by_id_and_version():
    p = load_prompt("echo", "v1")
    assert (p.id, p.version) == ("echo", "v1")
    assert "hello" in p.render({"word": "hello"})


def test_missing_prompt_version_fails_loudly():
    with pytest.raises(FileNotFoundError):
        load_prompt("echo", "v99")


def test_record_then_replay_round_trip(tmp_path):
    prompt = load_prompt("echo", "v1")
    RecordingAdapter(FakeLive(), tmp_path).extract(prompt, {"word": "abc"}, Echo)
    replayed = ReplayAdapter(tmp_path).extract(prompt, {"word": "abc"}, Echo)
    assert replayed.parsed == Echo(word="abc", confidence=0.9)


def test_replay_never_answers_for_unrecorded_input(tmp_path):
    prompt = load_prompt("echo", "v1")
    RecordingAdapter(FakeLive(), tmp_path).extract(prompt, {"word": "abc"}, Echo)
    with pytest.raises(RecordingNotFound):
        ReplayAdapter(tmp_path).extract(prompt, {"word": "different"}, Echo)


def test_low_confidence_goes_to_a_human():
    prompt = load_prompt("echo", "v1")
    low = AIResult(Echo(word="x", confidence=0.5), "m", prompt.id, prompt.version)
    high = AIResult(Echo(word="x", confidence=0.9), "m", prompt.id, prompt.version)
    assert needs_human(low, 0.75) and not needs_human(high, 0.75)


def test_confidence_must_be_between_0_and_1():
    with pytest.raises(ValueError):
        Echo(word="x", confidence=1.5)


def test_anthropic_adapter_passes_model_from_config_and_schema():
    calls = {}

    class FakeMessages:
        def parse(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                parsed_output=Echo(word="hi", confidence=0.8),
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    adapter = AnthropicAdapter("k", "some-model", 123, client=SimpleNamespace(messages=FakeMessages()))
    result = adapter.extract(load_prompt("echo", "v1"), {"word": "hi"}, Echo)
    assert calls["model"] == "some-model" and calls["max_tokens"] == 123
    assert calls["output_format"] is Echo
    assert (result.input_tokens, result.output_tokens) == (10, 5)


def test_anthropic_adapter_requires_a_key_when_no_client_is_injected():
    with pytest.raises(ValueError):
        AnthropicAdapter("", "m", 10)
