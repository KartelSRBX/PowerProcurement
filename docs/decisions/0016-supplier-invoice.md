# 0016. Supplier invoice on an order: typed in, compared by code, accepted by a person

Status: accepted (plan day 14)

## Context

An order ends with the supplier's invoice. Until now the app asked for the invoice (a letter) but never saw it, so nobody could say
whether what was invoiced is what was ordered, and the savings figures planned for later days (ledger, mismatch list) had nothing
to stand on.

## Decisions

- **A person types the invoice in.** Number, date, currency, total without VAT, VAT if wanted, and optionally the lines (quantity and
  unit price per requested item). Nothing is read from a mail or a file here; that can come later and would feed the same form.
- **One invoice per order** (`supplier_invoices.order_id` is unique). It can be replaced or removed until it is accepted. Partial
  invoices, credit notes and several invoices per order are not handled yet.
- **The comparison is computed, not stored.** `pipeline/invoices.compare` runs on every read against the offer behind the order, so
  a changed tolerance applies at once and the stored row cannot disagree with the order. It checks the total against the offer's
  total, and with lines each item's quantity (exactly) and unit price (within the tolerance), items missing from the invoice, and
  whether the lines add up to the total (a few cents of rounding are allowed; a larger gap is shown as possible freight, other
  charges or a typing error, never guessed).
- **Tolerance is a Settings value** (`invoice_tolerance_pct`, default 1%, 0 to 20) applied to the order total and to unit prices.
  Quantities have no tolerance: a short delivery is a fact a person should see.
- **Other currencies** are compared in EUR at the rate in Settings and the result says so; a difference caused by the rate then
  shows as a difference.
- **VAT is outside the comparison.** The offer is without VAT; the invoice's VAT is stored and shown, not checked, because VAT
  rates are not data this app holds.
- **Accepting is a person's act.** A differing invoice needs a reason; the acceptance, with the differences present at that moment,
  goes to the audit log. An accepted invoice is frozen. Nothing is paid or posted anywhere.

## Mismatch list (day 15)

- **Findings have kinds.** `compare` returns `issues` (a kind, words, the item where there is one) as well as the plain `reasons`:
  total, price, quantity, missing_item, lines_sum, foreign_line, duplicate_number. The list is built from the same function, so it
  cannot disagree with the order's own view.
- **Duplicate number** means the same supplier has another invoice whose number is the same after dropping everything but letters
  and digits and ignoring case. It is a warning to look, not proof: two different invoices can share a short number such as `1`.
  Another supplier's identical number is not a duplicate.
- **A currency difference is a note.** The same money in another currency matches; a gap caused by the rate shows as a total
  difference. (Day 14 treated the note itself as a difference; that was wrong.)
- **Largest amount first** in EUR, so the invoice that matters most is on top. Open invoices by default; accepted ones stay visible
  under their own filter with the reason they were accepted.

## Not decided here

- Savings against the baseline from matched invoices (plan day 16).
