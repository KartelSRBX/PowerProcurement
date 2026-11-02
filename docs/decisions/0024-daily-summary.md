# 0024. Daily summary

Status: accepted (plan day 23)

## Context

By day 22 the app held a dozen lists a buyer has to remember to open: letters to approve, late deliveries, urgent requests, invoices that differ, screenings
that fell due. The plan asks for one screen: what needs a person today.

## Decisions

- **It collects; it does not decide or send.** The summary reads records the app already keeps and counts them. It has no data of its own, sends
  nothing and changes nothing. Every line links to the page where the thing is handled.
- **Ten sections, each with its full count and the first eight lines:** urgent requests still waiting for a quote; letters waiting for approval; late
  deliveries; offers past or near their validity date; suppliers that have not answered a request for quotation; contracts that ended or end soon; bank
  details waiting for a second person; supplier invoices that differ from the order; supplier screenings that are overdue or need attention; strong,
  unreviewed duplicate-supplier pairs.
- **Silent means:** a request for quotation was sent at least N days ago (3 by default), no offer from that supplier has been entered for that request, and
  the request has no order yet. A supplier may be answering by mail that nobody has entered, so the line says "has not answered", not "ignored".
- **Offers and contracts:** an offer is listed when its validity date is past or within N days (3 by default) and its request has no order yet; a contract
  when its end date, as a person entered it in the legal module, is past or within N days (90 by default). A contract with no end date is not listed.
- **Suppliers never screened are not on the list.** On a new installation that would be every supplier. They are counted in a note and shown under Re-checks
  on the Suppliers tab; the summary lists screenings that are overdue or whose last result needs attention.
- **Thresholds are Settings** (days of silence, days before an offer or a contract runs out), changed by a named person and logged like the others.
- **A page, not a mail.** It is the Today tab with a count in the menu. A message sent each morning would be a new outward action and is left for the roles
  of days 24 to 25.

## Not decided here

- Per-person lists ("what needs me"): without sign-in the app knows only a typed name. After days 24 to 25 the summary can be cut by role.
- Snoozing or marking a line as seen. Each line goes away when the thing behind it is dealt with, which keeps the page honest.
- Mail or chat delivery of the summary.
