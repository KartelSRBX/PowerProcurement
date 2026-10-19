# Changelog

## 1.1 (2026-10-19)

Tasks in Bitrix24. Release 1 is the former 0.1.0 below.

### Added
- **Tasks in Bitrix24, Excel or a demo portal** (Tasks tab, panel on every request): a parent task per request and a subtask per step,
  statuses and people read back, history of changes, progress, drift warnings, Excel export and import. Everything that differs
  between companies (users, statuses, kanban stages, steps, custom fields) is a saved setting; see
  [ADR 0012](docs/decisions/0012-task-integration.md). Migration 0011, 14 new tests (131 on Postgres).
- **Not verified:** never run against a live Bitrix24 portal (scripted portal only).

## 0.1.0 (2026-10-18)

First release. The whole path runs end to end on synthetic data, with or without an AI key.

### What works
- **Request to order in eight steps:** email to structured request, supplier shortlist and target prices, letters to suppliers,
  offers and scoring, customer quote with markup, recorded outcome, purchase order, invoice request.
- **One approval queue.** Every outgoing letter (supplier RFQs, customer quotes, follow-ups, reminders, order confirmations, delivery
  questions, invoice requests) leaves only after a named person approves it; real sending is off by default and demo mail goes to Mailpit.
- **AI steps that only need a key** (Settings tab): email parsing and bulk parsing, extra supplier suggestions, letter drafts, reading
  supplier answers from pasted text or PDF / Excel / CSV files, follow-ups, customer reminders, reading the customer's reply, order
  confirmation, delivery question, plain-language explanations of the score table and the analytics. Every step has a template or
  hand-entry fallback, and code, not the AI, computes every price, total, score and margin.
- **Suppliers:** profiles, check history, sanctions flag, sorting and cascading filters, encrypted two-person access vault.
- **Analytics:** message funnel, markup win-rate analysis with a suggested markup, National Bank of Serbia rates or manual rates.
- **Panel:** dark and light theme, one-command install with `docker compose up --build`.

### Fixed before the release (found by an independent review)
- A double click or two tabs could send the same letter twice: a letter is now claimed before sending and put back if sending fails.
- Two purchase orders for one request were possible; the database now enforces one (migration 0010).
- An AI-written letter is rejected when it states any amount other than the one code computed, and numbers must stand alone
  (a required `5` no longer matches `15`).
- Running supplier discovery again no longer undoes the suppliers a person unticked; repeated AI notes no longer pile up.
- A later supplier answer can no longer rewrite an offer once a customer quote or order exists; no follow-ups after the order.
- A counter-offer read from the customer keeps its currency; the below-cost tag uses the server's rate, not a hard-coded one.
- Broken PDF / CSV files and oversized uploads give a plain message instead of an error.

### Known limits
- No AI call has been run against the live API in this repository: parsing accuracy and the quality of drafts are **not measured**.
- Scanned PDFs and photos are not read (no OCR); old `.xls` files are not read.
- Replies that arrive by email are not matched to a supplier automatically; paste the text or choose the file.
- No sign-in or roles: the name typed at the top is an audit label, not a login.
- The calculator tab is a placeholder; price sources are synthetic price lists.
- IMAP reading and the live NBS rate fetch are covered by mocks only.

Database migrations: 0001 to 0010. Tests: 117 on Postgres.
