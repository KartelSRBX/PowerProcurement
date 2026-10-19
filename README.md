# PowerProcurement

[![CI](https://github.com/KartelSRBX/PowerProcurement/actions/workflows/ci.yml/badge.svg)](https://github.com/KartelSRBX/PowerProcurement/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**From a customer's request email to an approved purchase order.** The app turns a request email into a
supplier-offer comparison, a customer quote with a markup, and a supplier purchase order. AI does the routine
work (reads the email, drafts letters, extracts terms from supplier replies). **A human approves every action
that leaves the system.** Scoring, prices and margins are plain deterministic code, never AI.

> **Status: working end to end, AI steps not measured yet.** The whole path runs on synthetic data and templates
> with **no AI and no outside accounts**: request, suppliers and target prices, letters with approval, offers and
> scoring, customer quote with markup, outcome, purchase order, invoice request. The AI steps (email parsing,
> drafting, extraction) have their interfaces, a gold set and an in-app key field, but their accuracy is
> **not published until a live run has been made** (see [Parsing accuracy](#parsing-accuracy)).

![Demo tour: email, request, suppliers, letters, approval queue, a supplier's Excel answer, follow-ups, scoring, quote, order letters, analytics](docs/img/demo.gif)

*The tour was recorded with a scripted stand-in for the AI (no live API call), so it shows the flow and the controls, not real model quality.*

## Contents

1. [What it does](#what-it-does)
2. [What the AI is for](#what-the-ai-is-for)
3. [Install and run](#install-and-run)
4. [First five minutes](#first-five-minutes)
5. [The panel, tab by tab](#the-panel-tab-by-tab)
6. [How the numbers are computed](#how-the-numbers-are-computed)
7. [Safe by default](#safe-by-default)
8. [Turning on the AI](#turning-on-the-ai)
9. [Configuration reference](#configuration-reference)
10. [Architecture and repository layout](#architecture-and-repository-layout)
11. [Develop and test](#develop-and-test)
12. [Troubleshooting](#troubleshooting)
13. [Roadmap](#roadmap) · [License](#license)

## What it does

A trading or procurement desk gets a request ("500 pcs of this microcontroller and 2000 capacitors") and has to
find suppliers, ask for prices, compare answers, quote the customer and place the order. PowerProcurement keeps
that whole path in one place, in eight steps:

| Step | What happens | Who does it |
| --- | --- | --- |
| 1. Request | An email becomes a structured request (items, quantities, category, language, deadline) | AI proposes (or you type it), **a person confirms** |
| 2. Suppliers | Suppliers that cover the items, are not sanctioned and did not fail their latest check are shortlisted | Code |
| 3. Target prices | Price lists give a target price per item, converted to EUR with the bank rate | Code |
| 4. Letters | Supplier letters are drafted in the supplier's language; **nothing is sent until a person approves** | Template or AI drafts, **a person approves** |
| 5. Offers | Supplier answers are compared and scored on price, lead time, reliability, terms and external risk | Code (weights are yours) |
| 6. Quote | Customer price = cost × (1 + markup), with a live margin preview and a markup hint from history | Code, **a person approves** |
| 7. Outcome | The customer's answer (accepted, rejected, counter-offer, silence) is recorded and feeds analytics | A person |
| 8. Order | Purchase order and invoice request, after the customer accepted and the budget checks pass | **A person approves** |

On top of that sit a mailbox, one approval queue, analytics, supplier profiles with due-diligence checks, an
encrypted access vault and a settings page where you enter your own API key.

## What the AI is for

A procurement desk spends most of its day on reading, matching, writing and chasing. That is where the AI works.
It is used as an assistant for **language and unstructured text** and nowhere else: it reads what people wrote,
proposes structure, drafts letters and explains results. It does **not** decide prices, scores or markups, does
not send anything and does not approve anything. Those stay in plain code and with a named person.

Every place below says what the AI does, what a person still does, and **what exists today**.
**Built** means it is in the code and works as soon as you paste an Anthropic key into **Settings**; without a key
the same step runs on a template or a hand-entry form, so nothing is blocked. **Planned** means designed, not coded.
Everything marked Built was tested against a scripted stand-in for the model (the repo has no key); it has **not**
been run against the live API, so read the first real answers critically.

| # | Job | What the AI does | What stays with code and people | Today |
| --- | --- | --- | --- | --- |
| 1 | Analytics of received requests | Classifies every email (request or not, language, category, confidence) and puts the numbers on **Message analytics** and **Pricing analytics** into words | Counting, funnels and forecasts are code; the words never change the numbers; a person decides what to do | Built: **Parse all with AI** in Mail, **Explain these numbers in words** on both analytics tabs |
| 2 | Understanding the request | Turns free text into items, quantities, budget, deadline, country; asks questions where it is unsure | A person confirms the request before anything is sent | Built (accuracy not measured yet) |
| 3 | Defining the supplier pool | Suggests suppliers the rules did not pick (by meaning, not keywords) and says why each candidate fits | Filters (category, sanctions, checks) are code and still apply; suggestions arrive **unticked**; a person ticks | Built |
| 4 | Preparing the supplier mailing | Drafts each letter in the supplier's language; also drafts the customer quote text | Code checks the draft (every item and quantity, the exact price) and falls back to the template; a person approves | Built |
| 5 | Collecting feedback | Reads a supplier answer (pasted, or a PDF / Excel / CSV / text file) into prices, lead time, MOQ, terms and gaps; explains the score table in words | **Code adds up the total**, warns about gaps; a person checks and saves the offer; scoring is code | Built (scanned PDFs without a text layer are not read) |
| 6 | Secondary mailing when something is wrong | Writes a precise follow-up for a silent supplier or an answer with gaps | Code decides **who** needs one; the letter waits in **Approvals** | Built |
| 7 | Invoice requests and the rest of the paperwork | Drafts the invoice request, the order confirmation to the customer, a delivery question to the supplier and a customer reminder; reads the customer's reply into a proposed outcome | A person edits and approves each letter and records the outcome | Built |
| 8 | Calculations (future) | Suggests customs codes from descriptions, reads supplier proforma and invoice fields, explains a calculation | The calculation itself is deterministic code | Planned (the **Calculator** tab is reserved) |

### 1. Analytics of received requests

Incoming email is classified as it is read, before anyone looks at it: *is this a request at all* (newsletters, payment
confirmations and thank-you notes are not), in which language, for which category, with what confidence. Three ways to
run it: **Parse with AI** on one email, **Parse all with AI** in the Mail tab (reads up to 20 stored emails that have no
request yet and reports how many were parsed, need review, or are not requests; press again for the rest), and the
mailbox reader (`cd backend && uv run python -m app.intake.poll`, from IMAP or a folder of `.eml` files).
That tagging feeds **Message analytics** (volumes per day, the funnel from email to order, languages, categories, top
senders, average AI confidence) and keeps the queue free of noise.

The AI does not produce the statistics: they are counted from database records, and the markup forecast in
**Pricing analytics** is a transparent model whose inputs you can see. The AI's only job there is the button
**Explain these numbers in words**: it gets the numbers the page shows and writes a headline and a few points
("win rate drops fast above 25% for this customer"). It cannot change a figure, and the text says which model wrote it.

### 2. Understanding the request

One prompt (`backend/app/ai/prompts/intake/v1.md`) reads the email
and returns a strictly typed result (`backend/app/intake/schemas.py`): is it a request, language, customer, category,
items with quantity, unit and part number, budget with currency, needed-by date, delivery country, a list of
questions and a confidence between 0 and 1.

The prompt is written to avoid the usual mistakes:

- **Never guess.** A missing or vague quantity, price, budget or date is left empty and becomes a question for the
  customer instead of an invented number.
- **Only the new text.** Quoted earlier messages are ignored.
- **Serbian, English, other.** Latin and Cyrillic script both work; European number format (`1.234,50`) and relative
  dates ("in two weeks", "end of the month") are resolved against the date the email arrived.
- **Part numbers stay as written** and are kept separate from the description.
- **Low confidence goes to a person.** Below `AI_CONFIDENCE_THRESHOLD` (0.75 by default) the email is stored as *needs review*
  instead of moving on, and a person **always** confirms the request before any supplier is contacted.

Use it in **Mail → Parse with AI** or **Parse all with AI** (needs your key, see [Turning on the AI](#turning-on-the-ai)). Its accuracy is
measured on a gold set of 16 emails with `python -m app.intake.evaluate --live`; **no figure is published until that
run has been made**.

### 3. Defining the supplier pool

The rules in `backend/app/suppliers/shortlist.py` run first and always: the supplier must serve the request's category,
must not be sanctioned, must not have a newest check of *not working*, and must have a price line whose key appears in the
item text. Suppliers are ranked by how many items they cover, then by past deals, and up to five are preselected.

What the rules cannot do is understand that "100nF 0603 capacitor" and "MLCC 0.1 µF, 0603, X7R" are the same part, or
that a request for "a rack UPS" belongs with a supplier of power equipment that never wrote the word "UPS". With a key set,
**Find suppliers and prices** also sends the request items, the shortlist and up to 40 other eligible suppliers (name,
categories, brands, notes, check result) to the model. It may do two things:

- add up to **five** suppliers the rules missed, each with a reason, marked **AI** in the list and **left unticked**;
- append a short "why" to the suppliers already on the list.

The model can only pick from the eligible suppliers it was shown, so it cannot put a sanctioned or failed supplier on the
list, and nothing is asked until a person ticks the box. If its confidence is below the threshold, or the call fails, the
list is exactly what the rules produced and a note says why.

### 4. Preparing the supplier mailing

For every shortlisted supplier the system prepares a request-for-quotation letter in **that supplier's language**
(Serbian or English today) with the items, the data we need back (unit price and currency, minimum order, lead time,
payment terms, warranty, validity) and the right subject with the request number. With a key set the model writes the
letter; without one, or if the draft fails the checks below, the fixed template is used. Each letter carries a tag
(**AI · model name**, **template**, or **template · AI draft rejected**) so you can see which it is.

The checks are in code, not in the model: the text must not be a stub or contain a placeholder like `[Name]`; an RFQ must
mention **every item and its quantity**; a customer quote must contain **the exact price and the lead time** that
code computed, so the model cannot quote a number of its own. The same drafting layer writes the customer quote text.

Either way nothing is sent: the drafts wait in **Approvals**, a person edits the text and approves or rejects each
one, and only then does it go out (to Mailpit in the demo).

### 5. Collecting feedback

Suppliers answer in free text, in different currencies and layouts. In **Step 5 · Offers and scoring → Enter a supplier's answer** you pick the supplier,
paste their reply, or choose the file they sent (PDF, Excel `.xlsx`, CSV or text), and press **Read with AI**. The model fills a typed form: unit price and currency per item, minimum order,
lead time, payment terms, warranty, validity, anything unusual (substitutes, partial coverage), and what is **missing**.
Then **code** takes over: it multiplies price × quantity per item, adds the total, checks that every item has a price and
that the minimum order fits, and shows warnings (for example when prices come in two currencies the total is left empty
for you to decide). You see an editable form with these numbers; **nothing counts as an offer until you press Save as
offer**, and the saved offer records that a model read it (`ai-reviewed`). Without a key the same panel opens an empty form
and you type the numbers.

Once offers exist, **Explain in words** below the score table writes a few sentences about why the ranking looks as it does.
The model is shown the numbers code computed and can describe but not change them; the ranking, the five criteria and
your weight sliders stay code (see [How the numbers are computed](#how-the-numbers-are-computed)). In the demo, **Simulate
supplier answers** still stands in for real replies so the rest of the flow can be shown without any real supplier.

**Files.** The app first turns the file into plain text and shows it to you under *Text read from the file*, so you can see
exactly what the model was given. PDF: the text layer of the first 30 pages. Excel: up to 5 sheets, 300 rows and 30 columns each,
read as values (a formula that was never calculated is empty). CSV and text in UTF-8 or Windows-1250. Limits: 5 MB, about
19,000 characters of text. Not read: scans and photos (no text layer, there is no OCR), password-protected files, old `.xls`
(save as `.xlsx`). In each case the app says why and you paste the text or type the numbers instead. With a key set, the file's
text is sent to the Claude API like any pasted answer.

![A supplier's Excel file read into the offer form](docs/img/ui/ai-file-upload.png)

The same reading skill is used on the customer's side (step 7).

### 6. Secondary mailing when something is not right

The **Follow-ups to suppliers** section finds suppliers that need a nudge. **Code decides who**: a supplier we wrote to who has not answered
after `FOLLOWUP_AFTER_DAYS` days (3 by default; you can override it with the "silent for at least N days" box), or one whose
saved answer is incomplete (a missing lead time or validity, items without a price, a minimum order that does not fit).
Nobody is asked twice about the same thing: a supplier already written to since their last message is skipped.
**Draft follow-ups** then writes one short, specific letter per supplier in their language, asking only for what is missing
("please confirm the lead time for item 2"), or the template when AI is off. The letters appear in the same **Approvals** queue
as every other letter and leave only after a person approves them.

### 7. Invoice requests and everything around the order

- **Customer's answer.** Under a sent quote, paste the customer's reply and press **Read with AI**. The model proposes
  *accepted*, *counter-offer* (with the price they named), *rejected*, *silence* or *unclear*. It is only a proposal:
  press **Record this answer** to save it under your name.
- **Reminder.** **Draft a reminder** writes a polite nudge to a customer who has not answered a sent quote. It is a draft
  in Approvals; only one waiting reminder per quote, and none once an outcome is recorded.
- **Invoice request.** After the customer accepts and a person approves the purchase order (budget and below-cost checks
  passed), **Prepare invoice request** shows the letter to the supplier (the order's items and total, drafted by the model
  or the template). You edit it and press **Approve and send to supplier**; it is not sent before that.
- **Order confirmation.** After the purchase order, **Draft order confirmation to the customer** writes the confirmation
  with the items, the exact price from the quote that was sent and the supplier's lead time; code rejects a draft that changes
  the price. It waits in Approvals. One per order.
- **Delivery question.** **Ask the supplier about delivery** asks for the dispatch date, carrier, tracking number and shipping
  documents. It waits in Approvals; you can ask again later once the first one is sent.

![Order letters waiting for approval](docs/img/ui/ai-order-letters.png)

### 8. In the future: calculations

The **Calculator** tab is reserved for the project's own landed-cost calculator. The plan for the AI there is
narrow on purpose: suggest the **customs tariff code** from a product description, read the fields of a supplier's
proforma or invoice (price, quantity, weight, origin), and explain a finished calculation in words. Duties,
freight, VAT and exchange rates are then computed by deterministic code from a rate table, so the same inputs always
give the same result and the result can be checked line by line.

### Ground rules for every AI step

- **Structured answers only.** Each step returns a typed object with a confidence value, not free text that code has to guess at.
- **Uncertainty goes to a person.** Low confidence, missing data and conflicts become questions and review items.
- **No numbers from the AI.** Prices, scores, margins, budgets and limits are code; the AI extracts, drafts and explains.
  Totals are added up by code from what the AI read, and a draft that changes a number is thrown away.
- **No action without approval.** Sending a letter, quoting a customer, recording an answer and placing an order each need a named human.
- **Every step has a fallback.** No key, a failed call, a low-confidence or rejected answer: the step still works on a template
  or a hand-entry form. Failed calls are written to the audit log (`ai.failed`).
- **Explainable and reproducible.** Prompts are versioned files (`backend/app/ai/prompts/<name>/v1.md`); calls go through one adapter;
  tests and CI use a scripted stand-in for the model, so CI never spends money or depends on a live model.
- **Optional and swappable.** Without a key the app runs on templates and rules. The model is a setting
  (`AI_MODEL`), and everything that talks to the outside world sits behind an adapter.
- **You control the cost.** With a key set, the model is called only by these actions: Find suppliers and prices, Draft
  letters, Quote this (quote text), Read with AI, Explain, Draft follow-ups, Draft a reminder, Prepare invoice request, Draft order confirmation, Ask the supplier about delivery, a supplier file read, Parse
  with AI and Parse all with AI. Calls are billed to your own key; with the provider on `mock` none of them calls anything.

## Install and run

You need **[Docker](https://docs.docker.com/get-docker/) with Compose** and about 2 GB of free disk. Nothing else:
no Python, no Node, no database to install, no account, no `.env` file.

```bash
git clone https://github.com/KartelSRBX/PowerProcurement.git
cd PowerProcurement
docker compose up --build
```

The first start builds the images (a few minutes) and fills the database with **synthetic** demo suppliers.
When the log shows the frontend as healthy, open:

| What | Where |
| --- | --- |
| Web panel | http://localhost:3000 |
| Demo inbox (Mailpit), every outgoing email lands here | http://localhost:8025 |
| API health | http://localhost:8000/health/ready |
| API reference (interactive) | http://localhost:8000/docs |

**Stop and clean up**

| Command | Effect |
| --- | --- |
| `Ctrl+C` in the terminal | stops the containers |
| `docker compose down` | removes the containers, **keeps your data** |
| `docker compose down -v` | also wipes the database and the saved encryption key (a fresh start) |
| `docker compose up -d` | runs in the background |

If a port is taken, stop the program using 3000, 8000 or 8025 first. Windows and macOS: run the commands in a
terminal while Docker Desktop is running (on Windows, WSL 2 is the usual backend).

> Nothing leaves your machine. All outgoing email goes to Mailpit, the demo data is invented, and AI is off until
> you paste a key.

## First five minutes

1. Open http://localhost:3000. At the top right, type **your name** in the *Working as* box. Every approval and
   edit is recorded under it, and most buttons stay disabled until a name is there.
2. Open **Mail**, click **Load 16 demo emails**, pick an email and click **Confirm as request**.
   (Or use **Requests → Create request**, which comes with a sample prefilled.)
3. On the request page click **Find suppliers and prices**, then **Draft letters**.
4. Open **Approvals**, read a letter, edit it if you like and click **Approve and send (to Mailpit)**.
   The email appears in Mailpit at http://localhost:8025.
5. Back on the request: **Simulate supplier answers** (demo only, there is no real supplier), move the weight
   sliders, click **Score**, then **Quote this** on the supplier you prefer.
6. Approve the quote, click **accepted** as the customer's answer, then **Approve purchase order** and
   **Approve invoice request**.

Every outward step needs a name and is written to the audit log. The purchase order is refused before the
customer has accepted, when the order is above the budget limit, and when the agreed price is below cost.

## The panel, tab by tab

The left menu has twelve tabs. The top bar shows server and mail status, the AI state, a **dark / light theme
switch** (the first visit follows your system, the choice is remembered), a link to Mailpit and the *Working as*
name box.

![Light theme](docs/img/ui/theme-light.png)

### Requests

The home tab lists every request with its stage and has the form for a new one. Click a request number to open
its **pipeline page**: one page, eight steps, top to bottom, with the next action always named under the title.

![New request form and request list](docs/img/ui/requests-new.png)

**Create a request by hand.** Sender, subject, one item per line as `500 x part name` (quantity first),
category, the customer's language and an optional *needed by* date, then **Create request**. Items without a
quantity are accepted but block supplier lookup until you fill the quantity in.

**On the pipeline page**

| Step on the page | What to do | What you get |
| --- | --- | --- |
| Items | Review what was extracted | The confirmed item list |
| **Steps 2-3 · Suppliers and target prices** | **Find suppliers and prices**; untick any supplier you do not want to ask | A shortlist with a reason per supplier ("covers 2/2 items; 40 past deals; RS"), at most five preselected. With a key, extra suppliers suggested by the AI appear with an **AI** tag, unticked |
| **Step 4 · Letters** | **Draft letters**, edit the text, **Approve and send to Mailpit** or **Reject** | One letter per supplier in that supplier's language (Serbian, English), status `draft`, `sent` or `rejected`, with a tag showing who wrote it (**AI · model**, **template**) |
| **Step 5 · Offers and scoring** | **Enter a supplier's answer**: pick the supplier, paste their reply or choose a PDF / Excel / CSV file, **Read with AI**, check the form, **Save as offer** (without a key you type the numbers). Or **Simulate supplier answers (demo only)**. Then move the five weight sliders and **Score**; **Explain in words** | An offer per supplier; a ranked table with every criterion, landed cost in EUR and lead time; **Quote this** on a row |
| **Follow-ups to suppliers** | Set how many silent days count (optional), **Who needs a follow-up?**, **Draft follow-ups** | Letters for silent suppliers and incomplete answers; they wait in **Approvals** |
| **Steps 6-7 · Quote and outcome** | Set *Markup %* and the currency, approve the quote, then record the customer's answer: with the buttons, or paste their reply and **Read with AI**, then **Record this answer**. **Draft a reminder** if they stay silent | Quote with price, markup and cost tags; outcome `accepted`, `rejected`, `silence` or `counter-offer` (with the price they named) |
| **Step 8 · Order** | **Approve purchase order**, then **Prepare invoice request**, edit the text, **Approve and send to supplier**; **Draft order confirmation to the customer**; **Ask the supplier about delivery** | PO with its budget checks; the invoice request; two more letters in Approvals |
| Price journal | Read only | Every price event: supplier cost, quote draft, quote sent, with who did it |

![Suppliers and target prices](docs/img/ui/step-suppliers.png)

![Letters to suppliers](docs/img/ui/step-letters.png)

![Offers and scoring](docs/img/ui/step-offers.png)

![Customer quote and outcome](docs/img/ui/step-quote.png)

![Purchase order and invoice request](docs/img/ui/step-order.png)

**The AI steps on this page.** The screenshots below were taken with a scripted stand-in model (note the `demo-stub` tag),
not the live API, so they show the layout and the controls, not real model quality.

A supplier's answer pasted (or a file chosen) and read: the form is editable, the missing item is named, nothing is an offer until you save it.

![Supplier answer read, with a gap](docs/img/ui/ai-supplier-answer.png)

The score table with **Explain in words** (the explanation never changes the ranking):

![Score table explained in words](docs/img/ui/ai-explain-scores.png)

Follow-up letters for silent suppliers; they wait in **Approvals**:

![Follow-ups to suppliers](docs/img/ui/ai-followups.png)

The customer's reply read into a proposed outcome, and the invoice request shown for editing before it is sent:

![Customer reply read by AI](docs/img/ui/ai-customer-reply.png)

![Invoice request preview](docs/img/ui/ai-invoice-request.png)

Notes: a supplier on the sanctions list, or one whose offer does not cover every item, is **excluded** and cannot
be quoted. A quote priced below cost is flagged *below cost* and cannot become an order.

### Mail

A mailbox with **All / Inbox / Sent** folders, search, and a detail pane. In the demo it holds sixteen synthetic
emails in English, Serbian (Latin and Cyrillic) and German, including newsletters and thank-you notes that are
**not** requests. Real inbox reading uses IMAP (see [configuration](#configuration-reference)).

![Mail: list and detail](docs/img/ui/mail-detail.png)

For an incoming email that has no request yet you get the **Create a request from this email** panel:

- **Parse with AI** (visible when AI is on) sends the email text to the Claude API and shows what it understood
  with a confidence value; you still confirm it.
- **Parse all with AI** (left column, needs a key) reads up to 20 stored emails that have no request yet and reports how many
  became requests to review, how many need review, and how many are not requests. Press it again for the rest.
- With AI off, the item list is drafted by a simple text rule. **Check and fix it**, pick category, language and
  *needed by*, then **Confirm as request**.

![Parse all with AI in the Mail tab](docs/img/ui/ai-mail-parse-all.png)

For an email that already has a request: **Open pipeline**, **Match articles**, **To the offer**. Sent mail shows
who approved it.

### Approvals

One queue for every letter waiting for a person: supplier letters (RFQs), customer quotes, supplier follow-ups, customer
reminders, order confirmations and delivery questions. **Waiting for approval** and **Decided** tabs, filter by *All / supplier RFQ / customer quote / supplier follow-up /
customer reminder / order confirmation / delivery question*. A tag shows when the first version was written by the AI.

![Approvals with follow-up letters](docs/img/ui/ai-approvals-queue.png)

![Approvals queue](docs/img/ui/approvals.png)

Pick a letter, read it, **edit the text in place** (edits are saved with your decision), then **Approve and send
(to Mailpit)** or **Reject**. Warnings (for example a price below cost) show in red on the letter. The number
beside *Approvals* in the menu is the count of letters waiting.

### Message analytics

Counted straight from the database: incoming emails per day (14 / 30 / 90 days), the funnel from email to order,
request statuses, email languages and categories, top senders, supplier RFQ response counts, customers' answers
to quotes, and items per request. **Explain these numbers in words** (needs a key) adds a short written summary of what the page shows.

![Message analytics](docs/img/ui/analytics.png)

### Pricing analytics

How often a quote is accepted at each markup, and which markup earns the most (markup × win rate). Filter by
customer and category. The page shows quotes in view, acceptance rate, average markup, the average discount
customers asked for, and a **suggested markup** with the expected win rate and margin per euro of cost, a win
rate bar chart, a margin chart and a per-customer table. Bars with fewer than eight quotes are drawn faded.

![Pricing analytics](docs/img/ui/pricing.png)

- **Load synthetic history** adds 600 invented quotes with planted patterns so the analysis has something to
  show. Their source is labelled *synthetic*; quotes you make yourself are labelled *live* and join the
  statistics once the customer's answer is recorded.
- The suggestion is only a hint. In **Offer** a **Use 22.5%** button copies it into the markup box; a person
  decides on every quote.

### Suppliers

Supplier storage with profiles, filters, sorting and price lists. Everything on this tab can be edited and every
edit is logged with your name.

![Supplier profile with discounts and checks](docs/img/ui/suppliers-profile.png)

**Find and sort.** The search box looks in name, email, brands and product types. The dropdowns are **cascading**:
pick a country and the category and brand lists shrink to what exists there, with counts. Further filters: role
in a brand (*vendor, distributor, sub-distributor, reseller*), partner status and check result. **Click a column
title** to sort (click again to reverse); sorting runs on the server, empty values go last, ties break by name.
Sortable columns: supplier, country, status, check, deals, payment days, stock days, brands, price lines.

**Profile** (select a supplier, then edit under *Profile* and **Save profile**)

| Field | Meaning |
| --- | --- |
| Status | `new`, `approved`, `preferred`, `on hold` |
| Payment | `prepayment`, `on delivery`, `deferred`, `credit` |
| Stock delivery, days | Typical delivery time for items in stock |
| Brands | Comma separated; for each brand a role: vendor, distributor, sub-distributor or reseller |
| Product types | Comma separated |
| Website, contract note, credit line (with note), rebates | Free text and a tick box |
| Discounts by brand | A list such as *Texas Instruments: 10% from 100 pcs*; add and remove entries |

**Supplier facts used by scoring** are shown as tags (years in business, deals, payment days, warranty, VAT ID
verified, framework contract) with buttons to **+1 deal**, **mark/remove VAT mark** and **mark: sanctioned**. A
sanctioned supplier disappears from matching and mailings.

**Price list.** Each supplier has price lines (key, description, price, currency, MOQ, lead time, valid until).
Add a line by hand or **import a CSV**: choose a file or paste text, **Validate** (shows every row with its
errors), then **Import all or nothing**. Header and example:

```csv
keyword,description,unit_price,currency,moq,lead_time_days,valid_until
lm358,LM358 dual op-amp,0.21,EUR,100,5,2027-12-31
```

Commas, semicolons or tabs work as separators and a decimal comma is accepted (files up to 1 MB). One bad row
stops the import so a price list is never half-loaded.

**+ Supplier** opens the form for a new supplier (name, country code such as `RS`, categories, languages, sales email).

### Supplier checks

Is the supplier still reachable and still working? This tab keeps a **history of checks**: result (*working*,
*under review*, *not working*), who checked, who you spoke to, a note and the time. **The newest check counts.**

![Supplier checks](docs/img/ui/checks.png)

- Tabs filter by *All, not checked, working, under review, not working* with counts.
- Pick a supplier, choose a result, add the contact and a note, **Record check**. The same panel is in the supplier
  card under *Checks*, together with the full history.
- Effect on the pipeline: a supplier whose newest check is **not working** is **left out of new shortlists**.
  *Under review* stays in, with "check under review" added to the reason. Suppliers never checked stay in.

### Access vault

Logins and passwords for supplier portals, distributor shops, software and customer portals, kept encrypted.

![Access vault](docs/img/ui/vault-accesses.png)

- **Accesses.** Add an entry (category, name, site URL, login, password, comments), search and filter by
  category, edit or delete. Lists never contain logins or passwords. When you edit, leave login or password
  empty to keep the stored value.
- **Requests, two-person rule.** **Request view** needs a reason. A **different** person (a different name in
  *Working as*) sees it under *Requests* and clicks **Approve** or **Reject** with an optional comment. After
  approval the requester clicks **Show once**: the login and password appear once, **within 15 minutes** of the
  approval, and the request becomes `used`.
- **Log.** Opening the vault, requests, decisions, reveals, edits and deletes, with who and when, never with the secrets.

![Request, approve, show once](docs/img/ui/vault-requests.png)

![A revealed access](docs/img/ui/vault-reveal.png)

![Vault log](docs/img/ui/vault-log.png)

> **Honest limit.** The app has no sign-in: a name is typed into the top bar. The two-person rule is a process
> aid and an audit trail, not a lock, because anyone who can open the app can type a second name. Secrets are
> encrypted in the database (Fernet) and never reach a list, but run the app on a machine you trust.
> See [ADR 0009](docs/decisions/0009-profiles-checks-vault.md).

### Article matching

Two tabs. **Catalog search** looks through all price lists for a part, name or supplier (`stm32`, `0603`, ...).
**Request items** matches each item of a chosen request against the price lists and shows suppliers side by side:
price in the original currency, price in EUR per piece, MOQ, lead time, total for the requested quantity and a
*best price* badge; sanctioned suppliers are greyed out.

![Article matching for a request](docs/img/ui/articles-request.png)

![Catalog search](docs/img/ui/articles.png)

Matching is rule-based: a price-list key must appear in the item description or part number. It is **not AI**, so
an empty result means "no such key in the price lists", not "no such product exists". Add the part to a
supplier's price list on the Suppliers tab, or request an offer by hand.

### Offer

The offer builder: the pipeline's steps 5 to 6 on one screen with a **live margin preview**. Choose a confirmed
request, **Simulate supplier answers** (demo) and **Score**; the table lists offers with score, landed cost and lead time.
Click a row, set the **markup** (number box or slider, from -10% to 60%) and the currency (EUR, RSD, USD). Three
tiles show cost, customer price and margin in EUR and turn red when the price is below cost. **Create quote
draft** puts a letter in the approval queue.

![Offer](docs/img/ui/offer.png)

If the history has enough quotes you see a line such as *History suggests about 20.5% (expected win rate 61%,
based on category, 261 quotes)* with a **Use 20.5%** button.

### Calculator

A reserved tab. It reads **"Unique to the project"** and is where the project's own landed-cost calculator will go.

![Calculator placeholder](docs/img/ui/calculator.png)

### Tasks (Bitrix24, Excel)

![Tasks of a request with progress](docs/img/ui/tasks-request.png)

Each confirmed request can become a **task with subtasks** in Bitrix24: one parent task for the request, one subtask per step
(suppliers, offers, quote, customer's answer, order, invoice). The app then reads the statuses back, keeps the history of what
changed and when, and shows the **progress** of every task and of the whole request. A person presses **Create tasks**; nothing
is created on its own, and **no AI is involved** in this part: the plan, the progress and the warnings are computed by code.

Three modes, chosen on the **Tasks** tab:

- **Bitrix24 (API).** Cloud Bitrix24 through an *incoming webhook* (Developer resources, Other, Incoming webhook; give it the
  Tasks and Users permissions). Paste its address once; it is stored encrypted like the AI key. **Test the connection** and
  **Load people, groups and stages from the portal** fill the dropdowns below with your own people and stages.
- **Excel file only.** No connection. **Export** gives a list of tasks; update the statuses in Excel or in Bitrix24
  (*Export to Excel* there) and **import** the file back. Rows are matched by the Bitrix24 task number, or by request and key.
  Status words in any language are understood (`Завершена`, `In progress`, `done`, ...); add your own words in the settings.
- **Demo.** A simulated portal kept inside the app, so every feature can be shown without a Bitrix24 account. It says so on screen.

**Two Bitrix24 portals are never alike, so nothing company-specific is in the code.** One saved document holds it all:

| Setting | What it decides |
| --- | --- |
| People and roles | Which portal user each role (sales, buyer, manager, any you add) maps to; who is the author; who is responsible by default |
| Statuses | What each of your status codes means (`new / in progress / review / done / paused`); kanban stages can be mapped too and win over the code |
| Steps | Which steps become tasks, their titles and descriptions (`$ref`, `$subject`, `$customer`, `$items`, `$needed_by`), parent, role, due in N days, checklist, and at which request stage the step should be finished |
| Custom fields | Which of your `UF_` fields carries the request number, customer and so on; fixed extra fields (priority, tags) |
| Actions | Which Bitrix24 method sets each state when a person changes it from here |
| Everything as JSON | The same document, to copy to another installation or to a customer |

![Connection and settings](docs/img/ui/tasks-connection.png)
![What the statuses mean](docs/img/ui/tasks-statuses.png)
![Steps that become tasks](docs/img/ui/tasks-steps.png)

After each sync the page lists **status codes it did not understand** so you can add them to the map, tasks **deleted in the portal**,
and **drift**: a task still open although the request is past that step, or a task closed before the app shows the step done.
Bitrix24 stays the source of truth for status; changing a state here calls the matching Bitrix24 method and is recorded with your name.

Honest limits: this was written from Bitrix24's public REST documentation and tested against a scripted portal, **not against a
live Bitrix24 account**. Exact field names for flows (`FLOW_ID`), custom fields and kanban stages may need a small change on your
portal, which is why they are settings. Statuses are read by polling (a "Read statuses now" button), not by Bitrix24 events.
Bitrix24 REST needs a paid plan and allows about 2 requests per second; the client waits and retries when told to slow down.

### Settings

![Settings](docs/img/ui/settings.png)

- **AI (Anthropic Claude).** Provider (`mock` or `anthropic`), model, and your API key with **Save**, **Test key**
  (one 8-token call, reports the result in plain words) and **Remove key**. See [Turning on the AI](#turning-on-the-ai).
- **Exchange rates.** Choose *National Bank of Serbia (middle rate)* or *Manual* with the RSD and USD per 1 EUR
  numbers. **Fetch from NBS now** reads the current rate on demand; with NBS selected the app refreshes about every
  six hours, keeps every fetched rate with its date and keeps the last good one when a fetch fails. The bank
  itself has no free JSON feed, so the app reads the public mirror `kurs.resenje.org`; the address is itself a setting.

### Mailpit (demo inbox)

Every email the app "sends" (supplier letters, quotes, purchase orders, invoice requests) is caught by
[Mailpit](https://mailpit.axllent.org/) at http://localhost:8025. Open it to see exactly what a supplier or customer
would have received.

![Mailpit](docs/img/ui/mailpit.png)

## How the numbers are computed

Everything below is code you can read (`backend/app/scoring`, `backend/app/pricing`, `backend/app/quotes`). AI never
changes a number.

**Landed cost.** Goods price in EUR, plus a demo model of freight and duty as a share of goods value by supplier
country: RS 3%, DE/PL/HU 5%, TR 12%, CN 18%, any other country 10%. These are proposals, not real tariffs.

**Hard filters.** A sanctioned supplier and an offer that does not cover every requested item are excluded before
scoring and shown last with the reason. Suppliers whose newest check says *not working* never reach the shortlist.

**Score** = weighted sum of five criteria, each 0 to 100. Default weights are 30 / 20 / 20 / 15 / 15 and you can
change them with the sliders on every request (they are normalised, so only the proportions matter).

| Criterion | Default weight | How it is scored |
| --- | --- | --- |
| Price | 30 | 100 × (target or best landed cost) ÷ this offer's landed cost |
| Lead time | 20 | 100 if within the days available; otherwise minus 10 points per late day (without a deadline: 100 minus the lead days, at most 60 off) |
| Reliability | 20 | 10 + 4 per year in business (up to 10) + 20 if the VAT ID is verified + 2 per past deal (up to 15), minus penalties for flags such as an unverified tax ID |
| Terms | 15 | 30 for a framework contract + up to 30 for payment days (60 days = full) + up to 25 for warranty (24 months = full) + 15 if the MOQ fits |
| External risk | 15 | 100 minus a country penalty (RS 5, DE/PL/HU 0, TR 15, CN 20, other 10) minus penalties for flags such as reported customs delays |

**Quote.** Customer price = landed cost × (1 + markup), converted at the bank rate. The preview shows cost, price
and margin before anything is created.

**Markup hint.** Pricing analytics groups quotes by markup bucket, counts how often they were accepted, fits a
win-rate curve and suggests the markup that maximises expected margin (markup × win rate). It uses the narrowest group with
enough quotes (the customer's own history, then the category, then all quotes) and always says which one.

**Purchase order checks.** Only after the customer **accepted**; the cost must be within `PO_BUDGET_LIMIT_EUR`
(50,000 EUR by default); the agreed price must not be below cost; one order per request.

## Safe by default

- **Nothing is sent outside the machine.** All mail goes to Mailpit. Real sending is a separate flag
  (`MAIL_REAL_SEND_ENABLED`, off) and, when on, limited to the addresses in `MAIL_ALLOWED_RECIPIENTS`.
  Real sending is environment-only on purpose and cannot be switched on from the browser.
- **Every outgoing message needs a named human approver** (`backend/app/mail/sender.py`).
- **AI never decides numbers.** It extracts and explains. Answers are schema-validated and carry a confidence
  score; below the threshold (0.75 by default) the item goes to a person.
- **A person confirms every request** before any supplier is contacted.
- **Secrets are encrypted** before they reach the database (API key, vault entries) and are never sent back to
  the browser; logs and the audit trail never contain them.
- **Names are not sign-ins.** The top-bar name is an audit label. Run the app on a machine and network you trust,
  or put your own authentication in front of it, before storing anything real.
- **CI never calls the live Claude API.** It replays recorded answers (`backend/app/ai/replay.py`). Prompts are
  versioned files (`backend/app/ai/prompts/`).
- **Demo data is synthetic.** No real customers, suppliers, prices or emails. Forecasts shown on demo data say
  nothing about any real market.

## Turning on the AI

Optional. Without a key everything works on templates.

1. Open **Settings**, set *Provider* to `anthropic`, paste your own [Anthropic API key](https://console.anthropic.com/)
   and click **Save**, then **Test key**.
2. Set a spend limit in the Anthropic console first: calls are billed to your key.
3. That is all. The buttons that use the AI switch on: **Parse with AI** and **Parse all with AI** in Mail, extra suppliers and
   AI-written letters on the request page, **Read with AI** for supplier and customer answers, **Explain** buttons, follow-ups,
   reminders and invoice requests. Only these buttons spend tokens; the list is in [ground rules](#ground-rules-for-every-ai-step).
   Every one of them still works without a key, on a template or a hand-entry form.

The key is stored **encrypted** in the database; the encryption key is `APP_SECRET_KEY` or, if empty, a key generated
once into the `appdata` volume. It is never shown again and never goes back to the browser. A key saved in
Settings wins over `.env`. If you move the database to another machine, enter the key again.
Details: [ADR 0008](docs/decisions/0008-keys-in-app-and-nbs-rates.md).

### Parsing accuracy

16 synthetic gold emails (English, Serbian Latin and Cyrillic, German, and non-requests) live in
`backend/app/intake/gold/`. To measure the real model (a few cents; needs `ANTHROPIC_API_KEY` in the environment
or `.env`; keys saved in the Settings tab are used by the app, not by this command):

```bash
cd backend && AI_PROVIDER=anthropic uv run python -m app.intake.evaluate --live
```

The run records the answers, so later runs and CI replay them for free. **No accuracy figure is published here
until a live run has actually been made.**

## Configuration reference

Nothing is required. To change defaults copy `.env.example` to `.env` (never commit it). Values saved in the
Settings tab win over `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `powerprocurement`, `change-me`, `powerprocurement` | Database credentials for the compose database |
| `AI_PROVIDER` | `mock` | `mock` replays recorded answers; `anthropic` calls the live API |
| `AI_MODEL` | `claude-sonnet-5-5` | Model used for parsing and drafting |
| `AI_CONFIDENCE_THRESHOLD` | `0.75` | Extractions below this go to a person; AI pool suggestions below it are ignored |
| `FOLLOWUP_AFTER_DAYS` | `3` | Days without an answer before a supplier is offered a follow-up letter |
| `ANTHROPIC_API_KEY` | empty | Optional; you can enter it in Settings instead |
| `APP_SECRET_KEY` | empty | Fernet key that encrypts saved secrets; generated into the `appdata` volume if empty |
| `MAIL_REAL_SEND_ENABLED` | `false` | Real sending; off means everything goes to Mailpit |
| `MAIL_ALLOWED_RECIPIENTS` | empty | Comma separated allow-list used when real sending is on |
| `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | `mailpit`, `1025`, `procurement@demo.local` | Outgoing mail server and sender address |
| `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_FOLDER`, `IMAP_SSL` | empty, `993`, ..., `INBOX`, `true` | Read a real inbox; leave empty in the demo |
| `FX_SOURCE` | `manual` | `nbs` for National Bank of Serbia middle rates |
| `FX_RSD_PER_EUR`, `FX_USD_PER_EUR` | `117.0`, `1.08` | Manual rates, units per 1 EUR |
| `DEFAULT_MARKUP` | `0.15` | Starting markup until analytics suggests one |
| `PO_BUDGET_LIMIT_EUR` | `50000` | Largest purchase order the system approves |

Reading a real inbox over IMAP and live Claude calls have not been exercised against real servers in this
repository's tests; both are covered by mocks and recorded answers.

## Architecture and repository layout

```
Browser ──> frontend (Next.js) ──/api──> backend (FastAPI) ──> Postgres
                                              │
                                              ├── ai/       one adapter: replay | recording | Claude API
                                              └── mail/     one sender: approval required, Mailpit by default
```

| Path | What lives there |
| --- | --- |
| `frontend/app/` | The panel: one folder per tab (`suppliers`, `checks`, `vault`, `quote`, ...), shared `components/` and `lib/` |
| `backend/app/intake/` | Email to structured request, gold set, evaluation |
| `backend/app/suppliers/` | Shortlist and supplier profiles, checks, sorting |
| `backend/app/pricing/`, `scoring/`, `quotes/`, `orders/` | Target prices, scoring formulas, markup and quotes, purchase orders |
| `backend/app/rfq/`, `mail/` | Letters, approval queue, the single mail sender, mailbox |
| `backend/app/analytics/` | Message analytics and markup analysis |
| `backend/app/vault/`, `runtime/` | Encrypted access vault; runtime settings, secret encryption, exchange rates |
| `backend/app/ai/` | The AI adapter, versioned prompts, the one `run_task` helper every assisted step calls |
| `backend/app/worktasks/` | Tasks in Bitrix24 / Excel / demo: saved settings, providers, plan, status sync, progress, Excel in and out |
| `backend/app/assist/` | The assisted steps: supplier pool, letter drafts and their checks, supplier replies, follow-ups, explanations |
| `backend/migrations/` | Alembic migrations (0001 to 0011) |
| `docs/` | [Architecture](docs/architecture.md), [how the AI was directed](docs/ai-workflow.md), [decision records](docs/decisions/) |

Everything that talks to the outside world sits behind an adapter so it can be swapped or faked without touching
business logic. The rules above are enforced in code and covered by tests.

## Develop and test

Without Docker for the app itself (needs Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22 and a Postgres):

```bash
docker run -d --name pp-db -e POSTGRES_USER=pp -e POSTGRES_PASSWORD=pp -e POSTGRES_DB=pp -p 5432:5432 postgres:16-alpine
cd backend && uv sync
export DATABASE_URL=postgresql+psycopg://pp:pp@localhost:5432/pp
uv run alembic upgrade head && uv run python -m app.seed
uv run uvicorn app.main:app --port 8000                                       # API
cd ../frontend && npm ci && BACKEND_URL=http://localhost:8000 npm run dev     # panel on :3000
```

Checks, the same as CI (`.github/workflows/ci.yml`):

```bash
cd backend
uv sync
uv run ruff check . && uv run ruff format --check .
uv run alembic upgrade head && uv run pytest        # integration tests need DATABASE_URL (Postgres)
cd ../frontend && npm ci && npm run lint && npm run build
```

The backend suite has 131 tests (pipeline end to end, scoring, mail guard, settings, profiles and vault, analytics, the AI steps, file reading, order letters, the pre-release fixes and the task integration, with scripted models).
What a run looks like (real output, Postgres 16; the AI steps are tested with a scripted model, not the live API):

![AI-assisted steps: 16 tests](docs/img/tests/ai-steps-tests.png)

![Full suite, lint, types, migration](docs/img/tests/full-checks.png)

To see mail from a local run, start [Mailpit](https://mailpit.axllent.org/) on ports 8025 and 1025.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Buttons are greyed out | Type your name in *Working as* at the top |
| `port is already allocated` | Stop whatever uses 3000, 8000 or 8025 and run `docker compose up` again |
| The panel says *server unreachable* | The backend is still starting; wait for the compose log to show it healthy, then reload |
| *Parse with AI* is missing, or the *Explain* buttons are greyed out | AI is off: open Settings, choose `anthropic`, save a key |
| *Test key* says the key was rejected | Check the key in the Anthropic console; the app shows a plain reason (rejected, no access, model not found, rate limit, no network) |
| Vault says an access *cannot be decrypted* | The encryption key changed (new `APP_SECRET_KEY` or wiped volume); enter that access again |
| *Fetch from NBS now* fails | The rate mirror is unreachable from your network; the last good rate stays in use, or switch to *Manual* |
| Start over from scratch | `docker compose down -v`, then `docker compose up --build` |

## Roadmap

Each phase ends with an acceptance check; the next one starts only after it passes.

| Phase | Scope | Acceptance |
| --- | --- | --- |
| 0 | Scaffold: Docker, CI, database, AI adapter | `docker compose up` works, CI green (**done**) |
| 1 | Intake and parsing (step 1) | Parsing accuracy measured on a gold set of sr/en emails (**harness done, live measurement pending**) |
| 2 | Suppliers and prices (steps 2-3) | Shortlist and target prices for demo requests in three categories (**done on synthetic data; CSV price-list import; supplier profiles, checks, sorting; exchange rates from the National Bank of Serbia; live price sources pending**) |
| 3 | RFQ and approval queue (step 4) | Letters go through the approval queue into Mailpit (**done; letters are drafted by the AI when a key is set, otherwise from templates**) |
| 4 | Offers and scoring (step 5) | Comparison table; scoring covered by tests (**done**) |
| 5 | Customer quote and outcome (steps 6-7) | Quote passes markup approval; outcome recorded (**done**) |
| 6 | Order and invoice request (step 8) | End-to-end: email, quote, PO, invoice request (**done; the AI steps (supplier answers, follow-ups, reminders, invoice request) work as soon as a key is set, not yet run against the live API**) |
| 7 | Analytics and markup | Test recovers patterns planted in the synthetic data (**done; real outcomes will replace synthetic ones**) |
| 8 | Publication | README, demo GIF, AI work log; runs in a minute (**README and install done; demo video pending**) |

Also done: encrypted access vault, dark / light theme, task integration for Bitrix24 (built from the documentation, not yet run against a live portal). Not built: roles and sign-in, a detailed landed-cost
calculator (the Calculator tab is reserved for it), live price sources.

More: [architecture](docs/architecture.md) · [how AI was directed](docs/ai-workflow.md) ·
[decision records](docs/decisions/)

## License

[MIT](LICENSE)
