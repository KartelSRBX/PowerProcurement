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

**Not verified:** the live Claude API call (no key available); the GitHub Actions workflow has
not run yet (nothing is pushed). Its steps were run locally, except the Compose job's
`docker compose logs` failure branch.
