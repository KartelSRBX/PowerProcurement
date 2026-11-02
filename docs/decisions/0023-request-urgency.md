# 0023. Request urgency

Status: accepted (plan day 22)

## Context

Some customers need an answer today. The app had the customer's "needed by" date from the mail but no way to say "this one first", and no list of
what is late. Guessing urgency from the text of a mail would be a model deciding who gets served first, with no way to see why.

## Decisions

- **Urgency is set by a person**: an *urgent* flag, a *reply-by* date (when the customer has to get a quote) and an optional note. Each change is
  logged with the name and the previous values. A reply-by date in the past is refused when it is set or changed; an old date can stay while the flag or
  the note is edited. Nothing is read out of the mail text.
- **Reply-by is not the customer's needed-by.** The mail's "needed by" date is the goods; it is shown beside the reply-by date for context and never
  becomes it.
- **A request is answered when its quote is sent** (stage `quote_sent` or later). A draft quote is not an answer. Until then the request is open and,
  if flagged or dated, is on the board. The flag and the date stay on the record afterwards.
- **The board** lists open flagged or dated requests: overdue first (most late first), then due today, then urgent ones with no date, then those within
  the warning window (2 days by default, a Setting), then the rest. Mails marked "not a request" never enter. It shows the stage and the next step,
  so the reader knows what is holding it.
- **No side effects.** Urgency changes no score, price, letter or supplier choice, and sends nothing. Chasing a supplier for a late answer stays a separate,
  approved letter.

## Not decided here

- Escalation (mail to a manager when a request goes late). It needs the roles from days 24 to 25.
- Working days and holidays: days are calendar days.
- A reply-by date proposed by the app from the customer's needed-by date and typical lead times; it would be a forecast, not a record.
