# How AI was directed

A running log: what was delegated to AI, what the human decided, what went wrong and how it
was fixed. Entries are factual and added at the end of each phase.

## Phase 0: scaffold

**Delegated to AI (Claude):** repository layout, FastAPI backend skeleton, AI adapter with
record/replay, mail sender with safety guard, Alembic migration, Next.js shell, Docker Compose,
CI workflow, README and decision records.

**Decided by the human:**
- Project name, MIT license, English for code and docs, Russian for working discussion.
- Work happens in a cloud clone of the GitHub repo; nothing is pushed without an explicit "ok".
- Demo mode by default: all mail to Mailpit, real sending off, human approval for outward actions.

**Problems found and fixed during the phase:**
1. Migration container crashed on start: `No module named 'app'`. Alembic did not put the working directory on the import path. Fixed with `prepend_sys_path = .`.
2. `docker compose up --wait` reported success before the backend was ready, because the backend had no healthcheck. Added healthchecks and made the frontend wait for a healthy backend.
3. Frontend container stayed `unhealthy`: Next.js standalone binds to the container hostname, not all interfaces. Fixed with `HOSTNAME=0.0.0.0`.
4. TypeScript 7 could not resolve React JSX types, so type checks failed. Pinned TypeScript 5.
5. Lint failures from overlong lines and FastAPI's `Depends()` default (rule B008). Raised the line limit to 110 and allowed the documented FastAPI pattern.
6. Environment limit, not a code bug: this sandbox blocks `ghcr.io` and re-signs TLS inside builds. The Dockerfile installs `uv` from PyPI instead of copying it from ghcr.io; for the sandbox only, local base images with the proxy CA were used. The repository itself is unchanged by that workaround.

**Verified (run, not assumed):**
- `docker compose up --build --wait` brings up db, mailpit, backend and frontend, all healthy.
- 15 backend tests pass (including the Postgres integration test); ruff clean; frontend type-check and build pass.
- A test email sent through `MailSender` appeared in Mailpit.

**Not verified:** the live Claude API call (no key available).

**After the push:** the GitHub Actions run was green (backend, frontend, compose jobs).

## Phase 1: intake and parsing (step 1)

**Delegated to AI:** the request schema, parsing prompt `intake/v1`, 16 synthetic gold emails with
expected answers (English, Serbian Latin and Cyrillic, German, two non-requests, one with quoted
history, one with a vague quantity), the scoring harness, mailbox readers, tables and API.

**Decided by the human:** to start phase 1. Accuracy numbers must come only from a real run.

**Decisions the AI made and flagged:**
- The plan says IMAP, but Mailpit has no IMAP server (its `--help` lists SMTP and POP3 only). Demo
  input is a folder of `.eml` files; the IMAP reader is written but has not run against a real server. See ADR 0004.
- The gold set must not leak into the prompt. Examples that mirrored gold cases were removed from the prompt wording.

**Problems found and fixed:**
1. The prompt contained a literal `"$"`; the template engine treats `$` as a placeholder, which would have crashed rendering. Found on review, fixed with `$$`, and a test now renders every gold email into the prompt.
2. A gold keyword (`отпорник`) did not match its own plural in Latin script (`Otpornici`). The test caught it; keywords are now word stems, and scoring transliterates Cyrillic so script choice does not change the score.
3. `ruff --fix` deleted an import that a test appended later still needed; the next lint run caught it.

**Verified by running:** 34 tests pass (including Postgres); migration `0002` applies in Docker;
the API explains clearly when no recorded answer exists; a perfect fake parser scores 100% in the
harness, a wrong quantity or an extra item lowers the score, and a failing call is reported, not hidden.

**Not done:** the accuracy of the real model on the gold set. It needs a live run with an API key
(`uv run python -m app.intake.evaluate --live`), which has not happened. No accuracy figure exists yet.
