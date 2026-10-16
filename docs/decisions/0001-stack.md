# 0001. Stack

Status: accepted (phase 0)

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Postgres 16. Typed, easy to test, good fit for data and AI work.
- **Frontend:** Next.js (React). Chosen over plain React because it gives server rendering and a proxy to the API with no extra tooling. TypeScript is pinned to 5.x; TypeScript 7 failed to resolve React's JSX types in this setup.
- **Packaging:** `uv` with a committed lockfile.
- **Run:** Docker Compose (app, Postgres, Mailpit). CI also runs `docker compose up --wait` as the acceptance check.
- **Lint/format:** ruff.
