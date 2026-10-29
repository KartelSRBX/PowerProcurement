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

## Delay alert (day 11)

- **The list is computed, not stored.** `GET /orders/overdue` works out, when it is asked, which open orders are past their promised
  date. Nothing runs on a timer, so there is no job to fail silently and no alert that can be stale. When a scheduler exists the same
  function can feed it.
- **The question is a letter in the approval queue** (`Letter` of kind `delay`), like every other letter to a supplier: drafted by code
  or by the model, edited and approved by a named person, never sent by itself. The AI may write the wording; the checks require the
  reference, the items and the promised date, and forbid any other figure.
- **No nagging.** A question is not drafted while one waits for approval, nor within the follow-up interval (`followup_after_days`)
  after one was sent: the supplier has been asked and has had time to answer. A rejected question does not block a new one.
- **Not a verdict on the supplier.** An overdue order says only that the promised date passed. Why, and whether it was the supplier's
  fault, is for a person to record in the history (day 12 reads those records for supplier performance).

## Supplier performance (day 12)

- **Computed from the record, not stored.** `suppliers/performance.py` reads delivered orders, their date-change events and the
  offer's quoted lead time when the profile is asked for. No table, nothing to go stale.
- **On time, two ways.** Against the date in force at delivery (what the supplier last promised) and against the first date (the
  calculation or first confirmation). A supplier who moves the date each time looks fine on the first and poor on the second.
- **OTIF is only OT.** "In full" needs a received quantity, which the record does not have; it is reported as not measured, not
  guessed.
- **Too few orders.** Under 3 delivered orders the figures are shown with a note that they are too few; day 13 uses the same
  threshold before delivery history may affect scoring.

## Delivery history in scoring (day 13)

- **Off by default.** The weight is a Settings value (`weight_delivery_history`, 0 to 100); at 0 rankings are exactly what they were.
  It is set once for the app, not per request, because it changes with the data a company has, not with the request.
- **Needs enough orders.** A supplier counts only with at least `delivery_history_min_orders` (default 3, at least 2) delivered orders
  that had a promised date. Otherwise the criterion is left out for that supplier, the other weights are renormalised, and a note
  on the row says why. A supplier is never given an invented neutral score for lack of history.
- **Score.** The average of the on-time share against the date in force and against the first date. Late-by-how-much and lead-time
  spread stay on the profile for a person to read; they are not in the number.

## Not decided here

- Partial deliveries, several shipments per order, and goods received against order lines. The record is one date and one status
  per order.
