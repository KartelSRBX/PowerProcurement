# 0002. AI behind one adapter, replayed in CI

Status: accepted (phase 0)

- All model calls go through `AIAdapter.extract(prompt, variables, schema)`. The model name comes from config (`AI_MODEL`), default `claude-sonnet-5-5` (a cost-conscious default for extraction and drafting; change per task if measurement shows a need).
- Answers must be pydantic models that extend `Confident` (a 0..1 confidence). `needs_human()` compares it to `AI_CONFIDENCE_THRESHOLD`.
- `RecordingAdapter` saves live answers; `ReplayAdapter` serves them by a hash of prompt id, version and rendered text. CI and the public demo use replay, so they cost nothing and are deterministic.
- Live adapter uses the official `anthropic` SDK (`messages.parse` with a schema). It is covered by a unit test with a fake client; it has **not** been run against the live API yet (no key in this environment).
- Not enabled yet: server-side refusal fallbacks and prompt caching. Revisit in phase 1 when real prompts exist.
