# 0017. Savings ledger: a stated baseline, negotiated and realized savings

Status: accepted (plan day 16)

## Context

"We saved money" is the claim a procurement team is asked to prove, and the easiest one to inflate. The app already holds the
offer behind each order and, since day 14, the supplier's invoice. What it lacked was the third number: what the goods would have
cost otherwise.

## Decisions

- **The baseline is a person's statement with a stated basis, never a default.** Three bases: the dearest offer on the same request
  that covered every item; the market target price; an amount typed with a note saying where it comes from. No baseline, no row: the
  ledger says how many orders have none and does not guess.
- **A data-based baseline is copied at the time it is set**, from the data then, not from the caller. Later offers or prices do not
  change a figure already reported. A typed one needs an amount and a note. Setting, changing and clearing a baseline go to the
  audit log with the previous value.
- **Two savings, named plainly.** Negotiated = baseline minus the offer behind the order. Realized = baseline minus the invoice,
  and only for an invoice a person has accepted (day 14). Realized totals include only orders with such an invoice, so they are never
  set against invoices nobody has checked; the number accepted despite a difference is shown beside them.
- **Goods only.** Amounts are without VAT, in EUR at the Settings rates, on the goods price. Freight, duty and other landed-cost parts
  are not in the ledger; mixing them would compare a baseline that excludes them with a cost that includes them.
- **A negative saving is shown.** If the baseline is below what was paid, the row says so; the ledger does not floor at zero.
- **The market target can be far below the agreed price** when prices are fetched from a different market; as a baseline it then
  shows an overspend. That is what the data says; the person chooses which basis is fair.

## Not decided here

- Savings by month, by buyer or by category, and a comparison with the first offer of the same supplier (the app does not keep the
  history of a supplier's offers).
- Partial invoices and credit notes: one invoice per order (see 0016).
