# 0027. A second person by risk

Status: accepted (plan day 26)

## Context

Bank changes and vault access already need a different person, whoever the order is for. A purchase order is the step that commits money and
goes to the supplier, but one approval was enough for any amount, any supplier and any state of the contract. Which orders deserve a second pair
of eyes is the company's call, not ours, so the numbers are Settings and not code.

## Decisions

- **Four rules, each off until the company sets it.** A total above N EUR; a supplier with no delivered order yet; a supplier whose bank account was
  changed (approved) in the last N days; a linked contract with an open red remark. We do not know the company's limits and will not guess them, so
  all four start off and "In use" in Settings says so.
- **The first approver asks, a different person confirms, and only the confirmation creates the order.** When an order meets a rule, approving it
  records an ask (`second_approvals`) and answers 202 with the rules it met; nothing is created and no mail goes to the supplier. A different person
  confirms (or rejects, with a reason). Confirming creates the order with the first person as the approver and the second as `second_by`, then sends
  the usual letter. The first approver cannot confirm their own ask, whatever the case of the name; with sign-in on, the middleware makes the name true.
- **The same checks still run.** Quote accepted, budget limit, not below cost and the legal sign-off are checked again at confirmation, because a
  day may have passed. If they fail the ask stays pending and the reason is shown.
- **Asking again renews the waiting ask** (the new asker is then the one who cannot confirm); a rejection stays as history and the first approver can
  ask again. Every ask, confirmation and rejection is in the audit log, and the risks are stored with the order's approval record.
- **Rules read facts and never score.** A met rule changes no score, ranking, price or letter. It only holds the order until a second person agrees.
- **Roles.** Confirming is an approval: approvers (and administrators). Reading the risks and the list of asks is open to everyone signed in. The
  Today page lists the orders waiting for a second person.

## Not decided here

- Second person for other steps (a large invoice, a quote above a margin). The table and the settings are built to be reused; add them when asked.
- A "new supplier" test by age or by country. Only the plain fact "no delivered order with us" is used.
- Timeouts for an ask that nobody confirms. It stays on the Today page until someone decides.
