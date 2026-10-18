# 0011. Supplier answers as files, and the two order letters

Status: requested by the user (2026-10-18: read PDF and Excel from suppliers, order confirmation and delivery questions,
new demo GIF); the design below is the AI's proposal. Builds on [ADR 0010](0010-ai-assisted-steps.md).

## Decisions

- **Files become text first, and the text is shown.** `app/assist/files.py` turns PDF (text layer, first 30 pages, `pypdf`),
  Excel (`.xlsx`/`.xlsm`, values only, 5 sheets x 300 rows x 30 columns, `openpyxl`), CSV and text into plain text. That text goes
  through the same reading step as a pasted answer, is stored as the reply's text and is shown next to the form, so a person sees
  what the model was given. No new decision power: the total is still added up by code and nothing is an offer until saved.
- **Refuse, do not guess.** A PDF without a text layer, a password-protected file, a corrupt or oversized (5 MB) file, old `.xls`
  and unknown types are refused with a plain reason and a way out (paste the text, type the numbers). No OCR: it would add a heavy
  dependency and a new source of silent errors.
- **Upload as JSON (base64)** rather than multipart, to avoid another dependency; the size limit keeps requests small.
- **Two more letters, same rules as every letter.** `confirmation` (to the customer) carries the items, the **exact price of the
  quote that was sent** and the supplier's lead time; code rejects a draft that lacks them and falls back to the template.
  `delivery` (to the supplier) asks for dispatch date, carrier, tracking and shipping documents. Both are rows in `letters`
  (new nullable `order_id`, migration 0009), wait in the approval queue and leave only on a named approval. One confirmation per
  order; a delivery question may be repeated once the previous one is sent.
- **The demo GIF is recorded with the scripted stand-in model** and says so in every frame and under the image.

## Tested how

`backend/tests/test_files_orders.py` (12 tests): readers with generated PDF, Excel, CSV and text, every refusal, the upload through
the API with the model on and off, and both order letters with the model on, off and returning a bad draft.

## Not done

- OCR for scans; legacy `.xls`; images pasted into a reply.
- Reading several attachments of one email at once (one file per answer).
- Mail in the other direction: replies arriving by IMAP are not yet matched to a supplier and parsed automatically.
