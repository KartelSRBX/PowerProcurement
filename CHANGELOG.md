# Changelog

## Unreleased

Improvement plan, one change a day (one improvement and one commit per day, 21 Oct to 19 Nov 2026).

### Added
- **Offer terms (day 1):** an offer can now carry the price validity date, the Incoterms rule with its named place, and payment
  days. All optional. Entered when a supplier answer is confirmed or an offer is added by hand; the ranking table shows them and
  flags what a buyer should notice (no validity date, offer expired or expiring within 3 days, no Incoterms rule, rule without a
  named place). The flags are warnings only and do not change scores. Migration 0013, 4 new tests.
- **Prices per item and comparison (day 2):** an offer can carry a unit price and a minimum order per requested item. When it
  does, code decides whether the offer covers all items and whether the minimum orders fit (the tick boxes cannot contradict the
  lines). "Compare item by item" on the request page sets offers side by side in EUR, marks the lowest price per item among offers
  that can be compared, and says why an offer cannot be (only a total, missing items, different or missing Incoterms, expired
  price, sanctioned supplier); a stated total that differs from the sum of the lines is noted. Excel export of the same table.
  Migration 0014, 9 new tests.
- **Supplier mail finds its request (day 3):** mail arriving through the inbox poll is now sorted. A reply is matched to the
  letter it answers by the Message-ID that every approved RFQ now carries, else by the request number in the subject (PP-00012)
  together with the sender's address, else by the sender alone when only one request waits for that supplier. Matches are filed as
  "supplier answer"; doubtful mail goes to an "unattached" list on the Mail tab, where a person attaches it to a request and
  supplier or says it is not a supplier answer. Everything else still goes the customer-request way. Nothing creates an offer;
  reading the answer is day 4. Migration 0015, 9 new tests.
- **"Waiting to be read" on a request (day 4):** the offers step of a request lists the supplier mail the inbox filed under it.
  "Read" (with AI when a key is set, otherwise by hand) turns a mail into a supplier answer to check, exactly like a pasted one;
  a mail is read once, an unsaved reading can be reopened, and nothing becomes an offer until a person saves it. Attachments are
  not kept, so a file attached to the mail is uploaded in the form below. Migration 0016, 4 new tests.
- **Duty registry (day 5):** a customs tariff can be loaded into the app and searched by code or words (Settings, "Customs duties").
  Each line keeps the general duty, the unit and the rates under the trade agreements (SSP with the EU, CEFTA, EAEU and EFTA by
  country, TR, GB, CN, AE, EG) as printed, with the tariff's name, the date and who loaded it. A rate that is not a plain
  percentage (a table reference, a minimum, a sub-case with its own rates) is kept as text and marked "needs a look", never
  converted. For a code and an origin country the registry returns the general and the preferential rate side by side; a
  preference needs proof of origin and is never chosen automatically. A parser reads the official Serbian Customs Tariff 2026 PDF
  (10,280 lines read from the user's copy); the PDF and the parsed table are not in the repository, only the parser and a small
  invented sample in the same layout. Load: `python -m app.duty.loader --pdf ...` or a CSV from the Settings page. Migration 0017,
  11 new tests.
- **Landed-cost engine (day 6):** pure arithmetic in `app/pricing/landed.py` for what goods cost once they are in the warehouse:
  goods, origin charges, carriage, insurance, duty, customs agent, inland transport and VAT. The Incoterms rule of the offer decides
  which of these the seller's price already contains (EXW none, DDP all) and which the buyer adds from the figures a person gives.
  A needed figure that is missing is a warning and marks the result incomplete; nothing is guessed. VAT that can be reclaimed is
  shown but kept out of the landed cost. A simplified rule set for imports into Serbia, to be checked by a tax adviser; see
  [ADR 0014](docs/decisions/0014-landed-cost.md). Not wired into scoring yet (days 7-8). 12 new tests, each recalculated by hand.
- **Calculator tab (day 7):** the reserved tab is now the landed-cost calculator. It starts from a request and one of its
  offers (items, unit prices, currency, Incoterms rule, supplier country) or from items typed by hand, takes the costs of the
  whole shipment and a duty and VAT rate, and shows per item the customs value, duty, landed cost, cost per unit, VAT and
  cash out, plus a total breakdown. Shipment costs are split over the items by value. "Find duty" looks a tariff code up in
  the duty registry and offers the general and the agreement rate as buttons. New `POST /pricing/landed` and
  `GET /requests/{id}/landed-draft`. 7 new tests.
- **Landed cost in scoring, quotes and orders (day 8):** a calculation saved for an offer (migration 0018, `PUT
  /offers/{id}/cost`) becomes that offer's cost in scoring, the quote preview, the customer quote and the purchase order, when
  it is complete and the offer's price still matches. Otherwise the old flat estimate per country is used and says why. Every
  cost is labelled `calculation` or `flat estimate`; a quote stores its cost basis and breakdown. The Calculator restores a
  saved calculation and can remove it. 7 new tests.
- **Incoterms warnings and old rates (day 9):** the Calculator result lists, under the chosen Incoterms rule, which parts are
  in the supplier's price and which you pay on top, with the buyer's and seller's duty quoted from the Legal module's Incoterms
  data; an offer under EXW, FCA, FAS or FOB is flagged "you pay the main carriage". A calculation checks each tariff code
  against the duty registry and warns when the tariff's rates are older than a limit (new setting, 365 days to start with,
  changed in Settings, Customs duties), have no date, or the code is missing or partial. Warnings only: the typed rate is still
  used. 11 new tests.

## PP1.2

Legal: contract review.

### Added
- **Legal tab:** paste or upload a contract (.docx, .pdf, .txt); it is split into clauses, key terms are read out (payment days,
  advance, penalty and cap, liability cap, warranty, renewal, governing law, forum, Incoterms), and about 38 playbook checks flag
  risks from our side, buying or selling. Each remark quotes the contract, says why it matters, what to ask for and which law it
  rests on; a person accepts it, dismisses it or sends it to the lawyer. Reports as Markdown and Excel, a portfolio view with
  bottlenecks across contracts, a Contracts panel on each request, an optional sign-off rule that blocks the purchase order.
- **Norm base:** a catalogue of 53 acts (EU acts by CELEX number, CISG, the New York Convention, UNIDROIT, and national acts of Serbia,
  China and the UAE), loaded by a button, `python -m app.legal.loader --all`, or an uploaded file; split into articles and searchable.
- **Incoterms 2020:** our own structured summary of the 11 rules by 10 topics, used by the contract checks.
- **Optional AI read per contract** (off by default; quotes are verified, wrong ones dropped). See
  [ADR 0013](docs/decisions/0013-legal-module.md). Migration 0012, 22 new tests.
- **Loaded and checked (2026-10-19):** `loader --all` fetched 30 of the 53 acts (27 EU, CISG, New York Convention, UNIDROIT Principles;
  1,880 articles). All 27 CELEX numbers matched the titles EUR-Lex returned; 30 of the 39 playbook law references resolve to a loaded
  article and 9 name national acts that are not loaded.
- **Changed after the first live load:** the loader now takes the newest consolidated version of an EU act (it had fetched the text
  as first published, which for amended acts such as Regulation 833/2014 is outdated), and the article splitter reads untitled PDF
  articles, `Article IV`, `Article 1.1`, and ignores cross-references. The New York Convention and UNIDROIT got download addresses.
  Backend tests: 156.
- **Not loaded / not verified:** the 23 national acts of Serbia, China and the UAE (upload them; their names and numbers in the
  catalogue are unconfirmed); completeness of each article was spot-checked, not compared word by word; the starter thresholds are a
  draft; not legal advice.

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
