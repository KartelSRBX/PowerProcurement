# 0030. Draft checklists for CBAM and Serbian e-invoicing

Status: accepted as a draft (plan day 29)

## Context

Two rules change what a buyer in EU-Serbia trade has to do: the EU carbon border adjustment mechanism (CBAM) and Serbian electronic invoicing
through the SEF system. The project has no legal text of either loaded, and the law texts are the only thing that could be quoted as fact.

## Decisions

- **Every line is a draft and says where it came from.** A line carries the source address, whether that source is primary (the law, a government or
  EU page) or secondary (a law firm, a consultancy, a news site), a short passage copied from it, and the day the page was read (05.11.2026).
  The page says in a banner that this is a reading aid and not legal advice.
- **Dates carry their basis.** A date is `primary`, `secondary` or `inferred`. Anything not primary is tagged "check" in the list. The CBAM
  declaration date of 30 September 2027 is `inferred`: the pages read give 30 September of the year after the import year, not a date for 2026.
- **What was not found stays "not found".** The EUR-Lex pages gave only metadata and the Serbian law and rulebook texts are PDF attachments that
  were not opened; so CBAM rests on two secondary pages, and for Serbia the gazette numbers and titles come from efaktura.gov.rs. Lines such as
  foreign suppliers, imports and approve/reject deadlines say that nothing was found and ask a person to check. Nothing is filled in from memory.
- **Progress is recorded by a named person.** Each line is todo, done or not applicable; "not applicable" needs a note of at least three
  characters. Stored in `checklist_progress` (migration 0031), audited as `checklist.set`. Buyer and legal may change it, others read.
- **Nothing here computes, blocks or scores.** A checklist does not stop an order, a quote or a letter, and no duty or tax figure is derived from it.
- **The content is code, not data in the database.** The items live in `app/checklists/items.py` so that a change of wording or date goes through
  review and a commit, with the day it was read.

## Not decided here

- Checking the lines against the primary texts (law and regulation, rulebook PDFs) and promoting a line from draft to confirmed.
- Reminders before a date, or a per-order link to the CBAM threshold.
- Other regimes (customs declarations, VAT on imports).
