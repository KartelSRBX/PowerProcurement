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

## Not decided here

- A duplicate invoice number across orders and a list of everything that differs (plan day 15).
- Savings against the baseline from matched invoices (plan day 16).
