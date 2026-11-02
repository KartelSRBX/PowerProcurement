# 0022. Supplier re-checks: screening record, next date, beneficiary

Status: accepted (plan day 21)

## Context

A supplier that was clean a year ago may not be today, and the buyer is expected to show when they last looked and at what. The plan says
sanctions lists are not downloaded: no list is loaded in this project, and inventing one, or matching against one the app cannot show
to be current, would be worse than a plain record.

## Decisions

- **A screening is a record a person makes**: the date, the list they checked (named by them), the result (nothing found, a possible match,
  could not be decided) and a note. A match or an undecided result needs a note saying what was found. A date in the future is refused.
  Records can be removed; the removal is logged.
- **The app computes the next date, nothing else.** It is the last screening plus a period: a default in Settings (12 months), a period set on
  one supplier, or a date a person chose. A chosen date wins until a screening on or after it is recorded, which uses it up. Status is
  *never*, *current*, *due soon* (inside the warning window, 30 days by default) or *overdue*.
- **A match or an undecided result keeps the supplier on the list as needing attention** until a later screening says otherwise. It does not
  mark the supplier sanctioned, change a score or stop an order: that stays the deliberate, separate step it already is.
- **The beneficiary is a record too:** the names of the people who own the company in the end, where it was learned (business register
  extract, supplier declaration, other with a note), who confirmed it and when. No names, no problem: it can be recorded as "no natural person
  owns it" with a note. It goes stale on the same period as the screening. Names are not checked against anything.
- **One list for the buyer.** The Re-checks list on the Suppliers tab shows suppliers needing a person, attention first, then overdue, then
  never screened, then coming due, those with orders before those without. Suppliers on hold are left out. The order panel's "Pays to" line shows a
  tag when the supplier was never screened, is overdue, or has a result needing attention.
- **Months, not days.** A period is whole months added to the last date, the day clamped at the end of a short month.

## Not decided here

- Which lists a company must screen against. That is a legal question for the company; the app takes any name.
- Automatic screening against a downloaded list, or a link to one. It would need a source the project can show is current.
- Reminders by mail. The daily summary (day 23) will carry this list.
