# PowerProcurement

From a customer's request email to an approved purchase order. AI does the routine work
(reads the email, drafts supplier and customer letters, extracts terms from replies). A human
approves every action that leaves the system. Scoring and pricing are plain deterministic code.

> **Status: phase 1 of 8 (intake and parsing).** Email in, structured request out, with confidence and
> a human confirmation step. Parsing accuracy on the gold set is **not measured yet** (needs a live run).
> See the roadmap below.

## Run it

```bash
docker compose up --build
```

| What | Where |
| --- | --- |
| Web panel | http://localhost:3000 |
| API health | http://localhost:8000/health/ready |
| Demo inbox (Mailpit) | http://localhost:8025 |

No `.env` is needed for the demo. Copy `.env.example` to `.env` to change settings.

## Safe by default

- **Nothing is sent outside the machine.** All mail goes to Mailpit. Real sending is a separate
  flag (`MAIL_REAL_SEND_ENABLED`, off) and, when on, limited to `MAIL_ALLOWED_RECIPIENTS`.
- **Every outgoing message needs a named human approver** (`backend/app/mail/sender.py`).
- **AI never decides numbers.** It extracts and explains. Answers are schema-validated and
  carry a confidence score; below the threshold the item goes to a person.
- **CI never calls the live Claude API.** It replays recorded answers
  (`backend/app/ai/replay.py`). Prompts are versioned files (`backend/app/ai/prompts/`).
- **Demo data is synthetic.** No real customers, suppliers, prices or emails. Forecasts shown
  on demo data do not reflect any real market.

## Develop

```bash
cd backend
uv sync
uv run ruff check . && uv run pytest        # integration tests need DATABASE_URL (Postgres)
cd ../frontend && npm ci && npm run lint && npm run build
```

## Parsing accuracy

16 synthetic gold emails (English, Serbian Latin/Cyrillic, German, non-requests) live in
`backend/app/intake/gold/`. To measure the real model (spends a few cents, needs `ANTHROPIC_API_KEY`):

```bash
cd backend && AI_PROVIDER=anthropic uv run python -m app.intake.evaluate --live
```

The run records the answers, so later runs and CI replay them for free. No figure is published
here until a live run has actually been made.

## Roadmap

Each phase ends with an acceptance check; the next one starts only after it passes.

| Phase | Scope | Acceptance |
| --- | --- | --- |
| 0 | Scaffold: Docker, CI, database, AI adapter | `docker compose up` works, CI green |
| 1 | Intake and parsing (step 1) | Parsing accuracy measured on a gold set of sr/en emails (**harness done, live measurement pending**) |
| 2 | Suppliers and prices (steps 2–3) | Shortlist and target prices for demo requests in three categories |
| 3 | RFQ and approval queue (step 4) | Letters go through the approval queue into Mailpit |
| 4 | Offers and scoring (step 5) | Comparison table; scoring covered by tests |
| 5 | Customer quote and outcome (steps 6–7) | Quote passes markup approval; outcome recorded |
| 6 | Order and invoice request (step 8) | End-to-end: email, quote, PO, invoice request |
| 7 | Analytics and markup | Test recovers patterns planted in the synthetic data |
| 8 | Publication | README, demo GIF, AI work log; runs in a minute |

More: [architecture](docs/architecture.md) · [how AI was directed](docs/ai-workflow.md) ·
[decision records](docs/decisions/)

## License

MIT
