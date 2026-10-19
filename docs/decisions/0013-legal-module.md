# 0013. Legal: contract review on a playbook and a loaded norm base

Status: requested by the user (2026-10-19: download and store European trade law for goods, IT, electronics, apps and
subscriptions; the full Incoterms rules; other legal reference material; then analyse contracts, find bottlenecks and understand
risks). Answers given: jurisdictions EU, Serbia, CISG, China and the UAE; English only; contracts where we buy and where we
sell; AI reads a contract only per contract and on request; the starter playbook is marked as a draft; recommendations must
also highlight the risks. The design below is the AI's proposal.

## Decisions

- **The AI reads; rules decide; a person acts.** Deciding what is a risk is code in `app/legal/playbook.py` (about 38 checks over
  facts that `app/legal/analysis.py` pulls out of the text: payment days, advance share, penalty rate and cap, liability cap,
  warranty, notice periods, renewal, governing law, forum, Incoterms with place and edition, and so on). A model is never needed
  to produce a remark. When the AI is allowed, it only adds extra remarks, each with a quote.
- **Every remark quotes the contract.** The quote is checked to be a substring of the contract text; an AI remark whose quote is
  not found is dropped and counted. A remark carries why it matters, what to ask for, the law it rests on and who found it
  (rules or AI).
- **Law references are checked against what is loaded.** A rule cites an act and an article. The state is `verified` (act loaded
  and the article is in it), `article_missing` (act loaded, no such article) or `not_loaded`. The app never shows a statute text it
  did not load, and it does not pretend: with an empty base every reference reads "act not loaded yet".
- **The norm base is filled by the loader, not shipped in the repository.** 53 acts are listed in `app/legal/catalog.py`:
  EU acts by CELEX number (fetched from the EU Publications Office, then EUR-Lex; the newest consolidated version in force is preferred over the text as first published), CISG, the New York Convention and the UNIDROIT
  Principles, and national acts of Serbia, China and the UAE marked "check the name on import". The text comes by the
  *Load* button, `python -m app.legal.loader --all`, or an uploaded file (HTML, PDF, Word, text). Licences differ per source and
  the texts are the owner's to load; the repository carries only the catalogue.
- **Incoterms 2020 are our own structured summary**, not the ICC text: 11 rules by 10 topics (who delivers, risk, carriage,
  insurance, documents, clearance, checking, costs, notices, delivery point), a watch-out per side, and a list of what Incoterms do
  not cover. It feeds checks such as "a sea-only rule for a road shipment", "a named place is missing", "an outdated rule
  (DAT, DAF, DDU...)", "the edition is missing". The screen says to compare with the ICC publication.
- **The playbook is company policy and starts as a draft.** Thresholds, severity, on/off, "why it matters" and "what to ask for"
  are rows in the database, edited on the Playbook tab, and each save is audited. A rule keeps its *draft* tag until a person saves
  it. Approved governing laws and forums and the score weights are company settings (`legal_settings`).
- **Both sides.** A contract has our side (`buy` or `sell`); most checks apply to one side (for example, 100% advance is a risk
  when we buy and good news when we sell), and the report says which.
- **Decisions are recorded.** Each remark is open, accepted, dismissed or sent to the lawyer; a named person and a note are
  stored with the audit log. A new analysis keeps decided remarks. The score is the weighted count of open remarks (lower is
  better) and is a sorting aid, not a verdict.
- **AI is opt-in per contract.** `ai_allowed` is off by default; the page shows how many characters will be sent before the button
  is pressed; the contract text is untrusted input in the prompt (`contract_review/v1.md`).
- **An optional sign-off rule** (`require_signoff`, off) refuses to create a purchase order while a contract linked to the request
  has an open red remark. It is off because most users do not link contracts and it must never surprise them.

## Tested how

`backend/tests/test_legal.py` (22 tests, one needs Postgres): the catalogue, the article parser on an EUR-Lex-shaped page, a
scripted fetch, the browser-check and 403 messages, upload, search and the three citation states, the CLI, the Incoterms data,
that every check has a rule, buy and sell findings on two invented contracts with planted problems, Incoterms checks, decisions,
re-analysis keeping them, rule and settings updates, bad input, a Word file, the AI path with a scripted model, reports,
the portfolio and the sign-off gate. The Postgres test found a real bug (deleting a contract violated a foreign key that SQLite
ignores).

## Not verified

- **No statute text has been loaded or read by the author.** The build environment could not reach EUR-Lex, UNCITRAL or any other
  legal site. The loader's live behaviour (Cellar and EUR-Lex pages, browser checks) is tested only on a scripted site and an
  invented page.
- The CELEX numbers in the catalogue were written from the author's knowledge and could not be checked against EUR-Lex; a wrong one
  shows up as a failed load with a plain message.
- Article numbers cited by the starter rules come from the author's general knowledge and are shown as "verified" only after the
  act is loaded and contains that number. A wrong number is shown as "article not found", not hidden.
- The names and numbers of the Serbian, Chinese and UAE acts must be checked on import.
- The starter thresholds are a draft, not legal advice. Case law, national transposition of EU directives, scanned PDFs (no OCR)
  and languages other than English are out of scope.
- The AI review has not been run against the live API.
