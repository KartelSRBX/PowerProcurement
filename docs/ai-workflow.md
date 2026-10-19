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

## Walking skeleton (steps 2-8 without AI)

**Delegated to AI:** data model and migration, synthetic suppliers and price lists, shortlist,
target prices, letter templates, deterministic scoring with hard filters, quote/outcome/purchase-order
logic with budget checks, API, browser panel, tests.

**Decided by the human:** build a working skeleton now, without an API key.

**Decisions the AI made and flagged as proposals** (see ADR 0005): scoring formulas, shortlist order,
target price rule, purchase-order checks, default markup, demo exchange rates.

**Problems found and fixed:**
1. The first schema omitted whether an offer meets the minimum order quantity, which scoring needs. Caught while writing the offer simulator; the unpushed migration was regenerated.
2. Next.js standalone and the compose healthcheck issues from phase 0 were already fixed, so the new pages started healthy.
3. A sanctioned supplier must never receive a letter. Two layers now: it is excluded from the shortlist, and scoring excludes any offer from one with a reason. Both are covered by tests.

**Verified by running:**
- 46 tests pass, including a full API walk-through from request to purchase order and its refusal cases
  (no order before acceptance, none below cost, none without a named approver, nothing sent before approval).
- The same walk-through against the Docker stack with Postgres and Mailpit: 9 messages arrived in Mailpit.
- A scripted browser run (Chromium) clicked through every step in the panel to `invoice_requested`.

**Not done:** anything that needs a live model; the IMAP reader against a real server; real price sources;
analytics; ABC/XYZ; deploy.

## Mini-CRM panel (2026-10-16)

**Asked by the human:** a tabbed user panel: email window, message analytics, supplier storage,
article matching, offer builder.

**Built by the AI:** backend `app/crm/` (mail feed, analytics, supplier CRUD with audit, article search
and per-request matching, quote preview), migration 0004 (`inbox_emails`, send timestamps), the shell
and six tabs in the frontend, 5 new tests, ADR 0006.

**Problems found and fixed while verifying in the browser:**
1. Raw emails did not exist without AI parsing; added `inbox_emails` so the Mail window works without a key.
2. Running Alembic on SQLite broke on `now()` defaults, so verification moved to a real Postgres container (upgrade, downgrade, upgrade all pass).
3. My item-drafting rule missed the "NAME - 1000 pcs" format; fixed, and it stays a draft a person checks.
4. Layout bugs (grid left empty columns, table overflowed its card, chart text too small) found in screenshots and fixed.

**Verified by running:** 53 tests pass against Postgres; a scripted Chromium run went mail → request → article
matching → supplier letters → offers → quote draft → approved quote → analytics with no console errors.

**Correction (2026-10-17):** the first version of the panel text was in Russian, against the plan ("README, code and UI in English only"). Translated everything to English; the plan line was missed when writing the first version.

**Not done:** login, real inbound IMAP, anything that needs a live model.

## Phase 2 start: price-list import from CSV (2026-10-18)

**Asked by the human:** "move on along the roadmap". The AI proposed starting phase 2 with the main price channel from
the plan (supplier price lists), because it needs no API key and no source decisions.

**Built by the AI:** `POST /suppliers/{id}/catalog/import` (validate and preview, then apply), CSV parser with header aliases,
comma/semicolon/tab separators and decimal comma, per-row errors, duplicate keys in one file refused, expired
dates refused, a keyword the supplier already has is updated, apply is all-or-nothing and audited,
import panel in the Suppliers tab, 3 new tests.

**Decided by the AI, open to change:** an expired `valid_until` is an error (the pipeline ignores expired prices anyway);
file limit 1 MB and 5000 rows; rows are keyed by `keyword`, matching how article matching works today.

**Verified by running:** 56 tests pass against Postgres; in Chromium an invalid file showed per-row errors with import disabled, a corrected
file imported, and the new article was found in Article matching.

**Not done:** XLSX files, live distributor APIs, FX rate source, price history (an update overwrites the old price).

## Phase 2 acceptance and phase 3 queue (2026-10-18)

**Asked by the human:** "push, move on along the roadmap".

**Built by the AI:** a test that runs discovery for demo requests in all three categories (electronics, IT hardware,
other) and checks a shortlist of at least two suppliers, target prices for every item, no sanctioned supplier and every
price labelled unconfirmed. This closes the phase 2 acceptance criterion on synthetic data. Then the Approvals tab: one queue
of every supplier letter and customer quote waiting for a person, with editing, approve and reject, a decision history with
the approver's name, a warning when a quote is priced below cost, and a count badge in the menu. Backend `GET /approvals`, 2 new tests.

**Decided by the AI, open to change:** approving from the queue saves the person's edit first and then records the decision,
so the sent text is exactly what was reviewed; there is no bulk approve on purpose.

**Verified by running:** 58 tests pass against Postgres; in Chromium five drafts appeared in the queue, one was edited and approved, the count
dropped to four and the decided tab showed the edited text with the approver.

**Not done:** real price sources and an FX rate source (need the human's choice), AI-drafted letters (need a key).


## Phase 7: markup analytics (2026-10-18)

**Asked by the human:** "push and keep going".

**Built by the AI:** synthetic quote history with planted customer price sensitivity (600 quotes, 7 customers), live quotes
joined in once an outcome is recorded, win rate by 5% markup bucket, a logistic fit and a suggested markup with the basis
(customer, category or all quotes) and its sample size. A Pricing analytics tab with two charts and a customer table, and a hint
with a "Use" button in the Offer tab. Migration 0005, `GET /analytics/pricing`, `GET /analytics/markup-suggestion`, `POST /analytics/demo-history`, 4 tests.

**Decided by the AI, open to change:** [ADR 0007](decisions/0007-markup-analytics.md). The first version took the best bucket by raw
numbers; it jumped around between seeds, so it was replaced by a fitted curve.

**Verified by running:** 62 tests pass against Postgres, migration 0005 upgrades and downgrades; in Chromium the loaded
history gave 12.5% for the price-sensitive customer and 31% for the insensitive one (planted optimum is close to both).

**Not done:** real quote history import, the Offer hint was checked by types and the API but not clicked through in the browser because demo requests come from other senders than the synthetic customers.

## Phase 8 start: README visuals (2026-10-18)

**Asked by the human:** "push, keep going".

**Built by the AI:** a scripted browser tour on a freshly seeded database (demo email, request, supplier shortlist,
letter drafts, approval queue, offer, analytics), a 10-frame demo GIF (about 0.6 MB) and three screenshots in the README.

**Verified by running:** the tour ran end to end on Postgres with the mock AI; frames were looked at before they went in.

**Not done:** deploy to a server, public demo access, a short written walkthrough.

## Keys in the app, NBS rates, install from git (2026-10-18)

**Asked by the human:** no public demo, but anyone must be able to take it from GitHub and run it; users put their own
keys inside the application and the AI direction is finished; exchange-rate source is the National Bank of Serbia.

**Built by the AI:** a Settings tab (Anthropic provider, model, key with test; rate source with fetch and history), encrypted
key storage, migration 0006, `/settings` API, a **Parse with AI** button in Mail, NBS rate fetching with a stored history and
background refresh, compose volume for the encryption key, a rewritten install section in the README, 9 tests.

**Decided by the AI, open to change:** [ADR 0008](decisions/0008-keys-in-app-and-nbs-rates.md). The first idea was to keep
the key only in `.env`; the human's wish for entering it in the app replaced it.

**Verified by running:** 69 tests pass; on Postgres migration 0006 goes up and down; in Chromium a malformed key was refused, a
well-formed fake key was saved, never appeared in the page, was stored encrypted, and "Test key" got a real 401 from the Anthropic API.

**Not verified:** a successful call with a real key (none available here), and a live NBS fetch: this environment blocks that
host. The response format was read from the live service and the parser is tested against that format only.

## Supplier profiles, checks, access vault, sorting (2026-10-18)

**Asked by the human:** look at the first procurement tool, adapt four things from it (supplier profiles, supplier checks,
access vault, supplier sorting), add nothing else, and keep a "Calculator" tab labelled "Unique to the project".

**Built by the AI:** profile columns and discounts, check history with shortlist exclusion, cascading filters with server-side
sorting, an encrypted vault with two-person reveal and a log, three tabs and an upgraded Suppliers tab, migration 0007, 10 tests.

**Decided by the AI, open to change:** [ADR 0009](decisions/0009-profiles-checks-vault.md), including the honest limit that names are not sign-ins.

**Verified by running:** 83 tests pass on Postgres; migration 0007 goes up, down and up; in Chromium sorting, cascading filters, a
recorded check, and a vault request approved by a second name and revealed once all worked, and the list API never contained the password.

**Not verified:** real supplier data (only synthetic profiles are seeded; real data stays out of the repository).


## AI-assisted steps: only a key is needed (2026-10-18)

**Asked by the human:** build everything in the AI section of the README that was still a template or a plan, so that pasting an
Anthropic key is the only thing left to do. Calculations stay out.

**Built by the AI:** the `run_task` helper and ten prompts, the assisted steps (supplier pool suggestions, AI letters with code checks,
supplier-answer reading with code-computed totals, follow-ups, customer reminders and answer reading, invoice request preview,
score and analytics explanations, bulk email parsing), two tables and columns (migration 0008), the UI for all of it, 16 tests.

**Decided by the AI, open to change:** [ADR 0010](decisions/0010-ai-assisted-steps.md), in particular that follow-ups and reminders
go through the approval queue and that the invoice request is now previewed before sending.

**Problems found while testing:** a test expectation of mine was wrong arithmetic (the code was right); the "do not nag"
comparison used strictly-later timestamps and failed within one second (fixed to later-or-equal); the invoice letter shows the
supplier's currency, not EUR (test corrected).

**Verified by running:** 99 tests pass on Postgres; migration 0008 goes up, down and up; in Chromium the whole path ran against a
stand-in model (suggestion arrives unticked, AI-tagged letters, a supplier answer read and saved, gaps reported, scores explained,
follow-ups approved from the queue, customer reply read and recorded, reminder drafted, invoice previewed and sent, bulk parse, both
analytics summaries) and with the provider off every AI control was disabled with a hint and nothing returned an error.

**Not verified:** any call to the live API. The stand-in is not the model; answer quality, prompt wording in Serbian, and cost per
step are unknown until someone runs it with a key.

## Supplier files, order letters, new demo GIF (2026-10-18)

**Asked by the human:** read PDF and Excel from suppliers, add order confirmation and delivery question letters, rebuild the demo GIF.

**Built by the AI:** the file reader and upload endpoint (`pypdf`, `openpyxl` added for this), two prompts and templates, two letter
kinds with migration 0009, the UI (file chooser with the text shown, two buttons under each purchase order, new queue filters), 12
tests, an 11-frame GIF recorded in the dark theme with captions.

**Decided by the AI, open to change:** [ADR 0011](decisions/0011-supplier-files-and-order-letters.md): no OCR, upload as base64 JSON, one
confirmation per order.

**Verified by running:** 111 tests pass on Postgres; migration 0009 up, down and up; in Chromium an `.xlsx` was chosen, read, shown as text
and saved as an offer, both order letters appeared in the approval queue and the confirmation was approved.

**Not verified:** any call to the live API; real supplier PDFs and Excel sheets (only generated ones); the GIF and screenshots use a scripted
stand-in model.

## Review and fixes before release 0.1.0 (2026-10-18)

**Asked by the human:** polish what exists, check for bugs, prepare a release and a LinkedIn post.

**Built by the AI:** a second AI session reviewed the code read-only and reported 12 findings; the AI fixed the ones it could confirm:
double sending (letters claimed before sending), duplicate purchase orders (migration 0010), amount checks on AI letters, lost
shortlist ticks, offers rewritten after a quote, counter-offer currency, a hard-coded rate in the UI, file-reader errors; 6 new tests,
`CHANGELOG.md`.

**Verified by running:** 117 tests pass on Postgres; migration 0010 up, down and up; type check and lint clean.

**Not verified:** any call to the live API; the review itself is an AI reading code, so it can miss things. No sign-in exists, so the
approver name is a label, not proof of identity.

## Bitrix24 task integration skeleton (2026-10-19)

**Asked by the human:** automatic tasks and subtasks, status tracking, flows, authors, assignees and progress; connect by API or
by Excel export; cloud Bitrix24; a universal form that fits any organisation.

**Built by the AI:** feasibility check against the Bitrix24 REST documentation, then the whole skeleton: a validated settings
document, a Bitrix24 webhook client, a demo stand-in and an Excel mode, plan, creation, status sync with history, progress and drift,
Excel import that also reads Bitrix24's own export, the Tasks tab and the panel on each request, migration 0011, 14 tests.

**Decided by the AI, open to change:** [ADR 0012](decisions/0012-task-integration.md): configuration as data, polling instead of
events, a person presses the button, Bitrix24 owns the status.

**Verified by running:** 131 tests pass on Postgres; migration 0011 up, down and up; in Chromium the demo mode was configured,
tasks created, advanced and read back, and the screenshots in the README were taken from that run.

**Not verified:** any call to a live Bitrix24 portal. Field names for flows, custom fields and kanban stages come from the public
documentation and may need adjusting on a real portal.


## Legal norm base: first real load (2026-10-19)

**Asked by the human:** load the laws into the legal module's norm base.

**Done by the AI:** ran `python -m app.legal.loader --all` against a fresh Postgres with migration 0012 once the sandbox could reach
EUR-Lex, the EU Publications Office, UNCITRAL and UNIDROIT. 30 of the 53 listed acts loaded: the 27 EU acts, the CISG, the New York
Convention and the UNIDROIT Principles. Then checked what was loaded instead of trusting the counts: every CELEX number was compared
with the act title in the fetched text (all 27 matched), and article counts were compared with what the acts contain.

**Errors found and fixed:**
- The loader fetched the act as first published. For amended acts (the Russia sanctions regulations 833/2014 and 269/2014, the AI Act,
  consumer rights, the EMC, low voltage and radio directives, and others) that is outdated law. The loader now asks the Publications
  Office for the newest consolidated version in force and falls back to the original text only when none exists; the version used is
  stored in the act's note. Regulation 833/2014 went from 15 to 111 articles.
- The article splitter took the first sentence of an untitled PDF article (the CISG) as its title, kept extra spaces from the PDF,
  did not understand `Article IV` (New York Convention) or `Article 1.1` (UNIDROIT), and took cross-references such as `Article 76
  CISG...` for articles. Fixed, with tests.
- The catalogue listed the New York Convention and the UNIDROIT Principles as upload-only although their publishers offer the PDF; the
  addresses were added, and an already seeded database picks them up.

**Not loaded:** the 23 national acts of Serbia (9), China (8) and the UAE (6) have no official English text at a stable address, so
they are uploaded as files on the Norm base tab. Their names and numbers in the catalogue are still unverified. The text of none of
them was written by the AI.

**Not verified:** that every loaded article is complete (the checks were article counts and spot reads, not a word-by-word compare);
the UNIDROIT Principles parse to 210 articles and the expected total was not confirmed; the CISG was fetched from a UNCITRAL PDF that
also carries an introduction, which lands in the "preamble" entry. Laws change: reload to refresh the base.
