# 0015. Delivery record: what the supplier promised, what happened, and why dates moved

Status: part of the 30-day improvement plan (feature F7: know when goods are late). Day 10 is the record; the overdue list and the
question to the supplier come on day 11.

## Decisions

- **The record lives on the order.** `purchase_orders` gets `promised_date`, `delivery_status` and `delivered_date`; every change
  is a row in `delivery_events` (kind, old value, new value, reason, who, when). Events are only added, never edited.
- **A calculated date is not a promise.** A new order starts with the order date plus the offer's lead time, and the status
  "ordered, no confirmation yet". Only a person recording that the supplier confirmed moves it to "confirmed". Nothing in the
  system reads the supplier's mail and changes a date on its own: the AI reads and drafts, a person decides.
- **Moving a date needs a reason.** The first date of an order that has none needs none; any later change must say why
  ("supplier: stock arrives late"). The reason is what the supplier-performance step (day 12) reads to tell a slipping supplier
  from a changing customer.
- **Two end states.** `delivered` (with a delivery date: today unless given, never in the future, never before the order date) and
  `cancelled` close the record. A closed record is not edited; a correction would be a new, explicit decision.
- **Overdue is arithmetic.** An open order whose promised date is before today is overdue by the difference in days; a delivered or
  cancelled order never is. It is computed when asked, not stored, so it cannot go stale.
- **Orders made before this step have no date.** The migration leaves them empty rather than inventing one; the panel asks for a
  date, and the first one needs no reason.

## Not decided here

- Partial deliveries, several shipments per order, and goods received against order lines. The record is one date and one status
  per order.
