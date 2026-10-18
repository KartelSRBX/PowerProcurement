# 0010. AI-assisted steps: one key switches them on

Status: requested by the user (2026-10-18: "implement what is not implemented, so that only an AI key has to be pasted");
the design below is the AI's proposal.

## Decisions

- **One helper, `app/ai/tasks.py: run_task`,** is the only way an assisted step calls the model. It returns the typed answer
  or `None` plus a short reason (AI off, confidence below the threshold, call failed). Failures are written to the audit log
  as `ai.failed`; no step ever raises because the model did.
- **Every step has a fallback.** With the provider on `mock`, no key, a failed call, low confidence or a draft that fails the
  checks, the step runs on the template or a hand-entry form. The buttons that exist only for AI (Explain, Read with AI, Parse
  all) say so and stay disabled instead of failing.
- **The model reads, drafts and explains; code computes and checks.**
  - Supplier pool: candidates are filtered by code first (category, sanctions, newest check); the model may only pick from the
    list it was shown, at most five, and its picks arrive **unticked**.
  - Letters: RFQ text must name every item and quantity; quote text must contain the exact price and lead time code computed;
    stubs and placeholders are rejected. A rejected draft is replaced by the template and tagged `template · AI draft rejected`.
  - Supplier answers: the model returns per-item prices; **code** multiplies, adds the total, checks coverage and minimum order
    and warns on mixed currencies. A person edits and saves; only then is an offer created (`source = ai-reviewed`).
  - Follow-ups: code decides who needs one (silent for `FOLLOWUP_AFTER_DAYS`, or an answer with gaps, not already asked since
    their last message); the model writes the wording.
  - Customer answers: the model proposes an outcome; recording it is a separate click by a named person.
  - Explanations (score table, analytics): the model is given the numbers and returns words; nothing it says changes a figure.
- **New letters (follow-ups, reminders) are a `Letter` row in the same approval queue** as RFQs and quotes and leave only on a
  named approval. The invoice request is now shown and editable before sending, instead of going out on one click.
- **Provenance is stored and shown:** `drafted_by` on RFQs, quotes and letters (`AI · <model>`, `template`,
  `template · AI draft rejected`), `read_by` on supplier answers.
- **Prompts are versioned files** (`app/ai/prompts/<name>/v1.md`), rendered with `string.Template`.

## Tested how

A scripted stand-in model (16 tests in `backend/tests/test_assist.py`) covers each step with the model on, off, failing, unsure,
and returning text that breaks a rule. The live API has **not** been called in this repository (no key here); the prompts are
therefore untested against real answers. Run the app once with a key and read the first drafts critically.

## Not done

- PDF and Excel attachments of supplier answers (paste the text instead).
- Order confirmation letters and delivery questions (only the invoice request, reminders and follow-ups exist).
- Calculations and customs codes (the Calculator tab stays a placeholder).
- Measuring the quality of any step except parsing (`python -m app.intake.evaluate --live`).
