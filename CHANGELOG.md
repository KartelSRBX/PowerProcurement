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
- **Delivery record on an order (day 10):** a purchase order now has a promised date, a delivery status (ordered, confirmed,
  shipped, delivered, cancelled), a delivery date and an append-only history of changes with who and why (migration 0019,
  `GET`/`PUT /orders/{id}/delivery`). A new order gets a first date from the offer's lead time, marked as a calculation until a
  person records the supplier's confirmation. Moving a set date needs a reason; delivered and cancelled close the record; code
  counts the days overdue. A panel on the order in the request page shows and edits it. 6 new tests.
- **Delay alert (day 11):** `GET /orders/overdue` lists open orders past their promised date, most late first, with the state
  of the question to the supplier. `POST /orders/{id}/delay-question` (and `POST /orders/overdue/questions` for all) prepares a
  letter asking why the delivery is late and when it will come, with the promised date; it waits in Approvals as a "delay
  question" and nothing is sent until a person approves it. It is not drafted again while one waits or within the follow-up
  interval after one was sent. New AI prompt `delay_question_draft` with a template fallback in Serbian and English; the AI
  text is used only if it names the reference, the items and the promised date. The list is on the Requests page. 7 new tests.
- **Supplier performance (day 12):** the supplier profile shows delivery performance computed from the delivery records of its
  delivered orders, with no new tables: share delivered on time against the date in force and against the first date, days late
  when late, how often the promised date was moved later, the real lead time (min, max, mean, spread) against the quoted one,
  and the latest orders. Fewer than 3 delivered orders are shown with a note that they are too few to judge by. "In full" is
  reported as not measured, because the delivery record has no received quantity. 7 new tests.
- **Delivery history in the ranking (day 13):** a sixth scoring criterion from the supplier's on-time record (the share of delivered
  orders on time, averaged over the date in force and the first date). It is off by default; its weight and the number of delivered
  orders a supplier needs are set in Settings, Scoring (`PUT /settings/scoring`, saved with the person's name). A supplier with
  fewer orders is scored on the other criteria only and the ranking says why. The request page shows a "delivery" column when
  the criterion is in use. No migration; 6 new tests.
- **Supplier invoice on an order (day 14):** a person types in the invoice for an order (number, date, currency, total without VAT,
  VAT, optional lines) and the app compares it with the offer behind the order: total, and per item quantity (exact) and unit
  price, missing items, and whether the lines add up. The tolerance is a Settings value (`PUT /settings/invoices`, 1% by
  default). A named person accepts it, with a reason when it differs; an accepted invoice is frozen. One invoice per order.
  Migration 0020 (`supplier_invoices`), `GET/PUT/DELETE /orders/{id}/supplier-invoice`, `POST .../accept`, 11 new tests.
- **Mismatch list (day 15):** `GET /supplier-invoices/mismatches` and a list on the Requests page show every invoice that differs
  from its order, largest amount first, with each difference named: total, unit price, quantity, missing item, lines that do not
  add up, unknown line, and a duplicate invoice number (same supplier, case, spaces and dashes ignored). Filter by kind; open,
  accepted or all. The duplicate check also shows on the order's own comparison. Change to day 14: a different currency is now a
  note on the comparison, not a difference by itself. No migration; 6 new tests.
- **Savings ledger (day 16):** a **Savings** tab. On each order a named person sets a baseline (what the goods would have cost): the
  dearest offer that covered every item, the market target price, or a typed amount with a note. Code works out the negotiated saving
  (baseline minus the offer behind the order) and the realized saving (baseline minus an accepted invoice), with totals, and
  exports the ledger to Excel. Amounts are goods without VAT in EUR; the baseline is kept as set. Changes are logged. Migration
  0021 (`savings_baselines`), `GET /savings`, `GET /savings/export.xlsx`, `PUT/DELETE /orders/{id}/savings/baseline`, 7 new tests.
- **Article signals (day 17):** the ranking on a request flags an offer whose unit price for an article is above the last price paid
  (accepted invoice with lines) or ordered for the same article by a threshold, or whose lead time is longer than the last order's
  by a number of days and percent. Warnings only; scores are unchanged. Articles are matched by part number, else description.
  Thresholds in Settings (`PUT /settings/signals`: 10%, 25% and 3 days by default). `GET /requests/{id}/signals` gives per-item
  detail. No migration; 8 new tests.
- **Alternates, end of life, authorized channel (day 18):** a person records, on the Article matching tab, a manufacturer and an
  end-of-life mark for an article and links articles as replacement or equivalent; on a supplier's profile they tick the brands the
  manufacturer authorized it to sell. A request shows end-of-life articles with their replacements, and an offer from a supplier not
  marked authorized for the article's manufacturer is flagged. Warnings only; the app decides none of it. Migration 0022
  (`article_records`, `article_alternates`, `suppliers.authorized_brands`), 8 new tests.
- **Supplier bank details (day 19):** an account is never typed straight in. A person proposes it on the supplier's profile with a
  record of the call that confirmed it (who at the supplier, on which date, and where the number called came from: the contract, a
  verified record, the official website or an explained source, never the mail that announced the change), and a different person
  approves or rejects it. The old account stays in force until then. The IBAN check digits are verified; the approver is warned when
  the IBAN country, the holder name or an account already used by another supplier does not fit. Stored encrypted with a hash for
  finding duplicates (day 20). A "Pays to" line on the order shows the account and warns for 30 days after a change.
  Migration 0023 (`supplier_bank_accounts`, `supplier_bank_changes`), 9 new tests, ADR 0020.
- **Duplicate supplier finder (day 20):** lists pairs of suppliers that may be one company: the same tax number (a new optional
  profile field), the same bank account (compared by hash, nothing decrypted) or the same or a very similar name once legal forms and
  spelling are ignored. A list on the Suppliers tab, a warning on a supplier's profile and on creating one. A person marks each pair
  "different companies" or "the same company" with a reason; a dismissed pair comes back when a new signal appears. Nothing is merged
  or blocked. Migration 0024 (`suppliers.tax_id`, `supplier_duplicate_reviews`), 9 new tests, ADR 0021.
- **Supplier re-checks (day 21):** a person records a sanctions screening on a supplier (date, the list checked, result, note) and the
  beneficiary (owner names, source, who confirmed and when). The app works out the next date from a period (12 months by default,
  changeable in Settings or per supplier, or a date a person sets) and a **Re-checks** list on the Suppliers tab shows what is overdue, never
  screened, coming due, or has a result needing attention. No list is downloaded and nothing is blocked or scored. The order panel's "Pays to"
  line flags an unscreened or overdue supplier. Migration 0025 (`supplier_screenings`, `supplier_compliance`), 9 new tests, ADR 0022.
- **Request urgency (day 22):** a person marks a request *urgent*, gives a reply-by date for the customer's quote and an optional note. An **Urgent
  requests** board on the Requests page lists what is still waiting for a sent quote: overdue first, then due today, then the rest, with the step and
  the next action. The flag and date show in the requests list; the warning window (2 days) is in Settings. Nothing is guessed from the mail text and
  nothing else changes. Migration 0026 (`customer_requests.urgent, respond_by, urgency_note, urgency_by`), 5 new tests, ADR 0023.
- **Daily summary (day 23):** a **Today** tab with one list of what needs a person: urgent requests waiting for a quote, letters to approve, late
  deliveries, offers past or near their validity date, suppliers that have not answered a request for quotation, contracts ending, bank details waiting for
  a second person, invoices that differ, overdue screenings, duplicate suppliers to review. Each section shows its count and the first lines, each line links
  to where it is handled; the menu shows the total. Nothing new is stored and nothing is sent. Limits (days of silence, days before an offer or a contract
  runs out) are in Settings. No migration; 7 new tests, ADR 0024.
- **Sign-in (day 24):** users with scrypt-hashed passwords and cookie sessions. Off by default (the old "name at the top" mode); an administrator creates
  the first user in Settings, adds the others and turns it on. From then on every request needs a signed-in user and every field naming the person
  acting must be that user's name, so no action can be recorded under another name. Lock after five wrong passwords, session expiry, sign-out, password
  change and reset (which end other sessions), an audit trail of sign-in events, `AUTH_FORCE_OFF=true` for recovery. Roles are stored here and enforced on
  day 25. Migration 0027 (`users`, `auth_sessions`), 14 new tests, ADR 0025.
- **Roles in action (day 25):** with sign-in on, each request needs a role (buyer, approver, legal, admin; a user may hold several): approvals only for
  approvers, settings and users only for administrators, the legal pages for legal and approvers. Whoever edited an RFQ, quote or letter, or entered a
  supplier invoice, cannot approve it. Refusals are audited as `auth.denied` with the reason. The vault `person` field is now checked against the
  signed-in name. One table of rules (`app/auth/rules.py`) with a test that every route is named. Migration 0028 (`edited_by` on RFQs, quotes and
  letters), 28 new tests, ADR 0026.
- **Second person by risk (day 26):** an order that meets a rule switched on in Settings (a total above N EUR, a supplier with no delivered order, a bank
  account changed in the last N days, an open red remark on a linked contract) is not created by one approval. The first approver asks, a different person
  confirms (or rejects with a reason), and only the confirmation creates the order and sends the letter. All four rules are off until the company sets
  them. The request page shows the rules an order meets and the waiting ask; the Today page lists orders waiting for a second person. Migration 0029
  (`second_approvals`, `purchase_orders.second_by`), 11 new tests, ADR 0027.
- **Hints for the reviewer (day 27):** every letter (RFQ, customer quote, follow-up, reminder, confirmation, delivery and delay question) keeps the plain template
  text for the same facts. The Approvals page shows what the letter says differently, line by line (or "same as the template"); an AI draft and a colleague's
  edit show the same way. Decisions now carry a time, and `GET /approvals/stats` with a new Letter review section on the Analytics page gives the time from draft to decision,
  approvals and rejections and how often the text was changed, for AI drafts and template drafts. Migration 0030 (`template_body`, `decided_at`), 7 new tests, ADR 0028.
- **ABC/XYZ on order history (day 28):** the Analytics page sorts the articles bought by spend (A, B, C by cumulative share) and by the steadiness of the monthly quantity
  (X, Y, Z by coefficient of variation), with a 3x3 matrix, a table you can filter by class and an Excel download (`GET /analytics/abc-xyz`, `/analytics/abc-xyz.xlsx`).
  Boundaries (80/95, 0.5/1.0), the history window and the minimum months for XYZ are in Settings. An order without prices per article is left out and counted;
  with too little history no XYZ class is shown. No migration, 8 new tests, ADR 0029.
- **Checklists for CBAM and Serbian e-invoicing (day 29):** a Checklists page lists 16 draft lines (8 for the EU carbon border adjustment
  mechanism, 8 for Serbian SEF). Each line shows its source, whether that is primary or secondary, a short quote, the date it was read (05.11.2026) and a
  "to check" question; dates not taken from a primary source are tagged. A buyer or legal person marks a line done or not applicable (with a note) under
  their name (`GET /checklists`, `PUT /checklists/{key}`). Gaps say "not found". Migration 0031, 6 new tests. See `docs/decisions/0030-regulation-checklists.md`.

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
