# Architecture

```
Browser ──> frontend (Next.js) ──> backend (FastAPI) ──> Postgres
                                        │
                                        ├── ai/     one adapter interface: replay | recording | Claude API
                                        ├── assist/ AI-assisted steps; code checks every draft
                                        └── mail/   one sender: approval required, Mailpit by default
```

Everything that talks to the outside world sits behind an adapter so it can be swapped or
faked without touching business logic: the model (`app/ai`), mail (`app/mail`), and later
price sources and risk checks.

## Rules enforced in code

| Rule | Where |
| --- | --- |
| AI answers are structured and carry `confidence`; low confidence goes to a human | `app/ai/base.py` |
| Prompts are versioned files, never edited in place | `app/ai/prompts/<id>/<version>.md` |
| Tests and CI replay recorded answers; an unrecorded input fails loudly | `app/ai/replay.py` |
| No mail without a named approver; demo mode sends only to Mailpit | `app/mail/sender.py` |
| Every change records who made it (`system`, `human`, `client`) | `audit_log` table |

## Modules

| Module | Role |
| --- | --- |
| `app/intake` | Email to structured request, gold set, evaluation |
| `app/suppliers`, `app/crm` | Shortlist, supplier profiles, checks, sorting, price lists |
| `app/pricing`, `app/scoring`, `app/quotes`, `app/orders` | Target prices, scoring, markup and quotes, purchase orders |
| `app/rfq`, `app/mail` | Letters, approval queue, the single mail sender, mailbox |
| `app/analytics` | Message analytics and markup analysis |
| `app/vault`, `app/runtime` | Encrypted access vault; runtime settings, secret encryption, exchange rates |

## Not built yet

Roles and sign-in, live price sources. See the roadmap in the README.
