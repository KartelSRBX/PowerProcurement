# 0026. Roles in action

Status: accepted (plan day 25)

## Context

Day 24 made the name in a request the true one. Roles were stored but did nothing: any signed-in person could approve their own work or change
settings. This day makes the roles mean something.

## Decisions

- **One table decides.** `app/auth/rules.py` lists, in order, which role each kind of request needs; the first rule that matches decides. A user may
  do whatever any of their roles allows; an administrator may do everything. A request that no rule names needs an administrator (it fails closed),
  and a test fails when a route of the app is named by no rule, so a new route has to be given a role on purpose.
- **Roles.** *buyer*: requests, suppliers, offers, orders, mail, tasks and the other everyday work, but not the approvals. *approver*: the decisions
  that let something go out or be paid (RFQ, quote and letter decisions, creating the order, accepting a supplier invoice, a bank change, a vault
  request), and nothing else that changes data. *legal*: contracts and legal rules; the legal pages are also readable by approvers. *admin*:
  users, settings, tariff import, the vault entries, the task connection, demo loaders.
- **Reading is open to everyone signed in**, except the legal pages (legal, approver, admin) and the vault list (buyer, approver, admin).
- **The approver is not the author.** Whoever last edited the text of an RFQ, a quote or a letter (now recorded as `edited_by`) cannot approve it, and
  whoever entered a supplier invoice cannot accept it. The bank-change and vault rules that already needed a different person stay as they were.
  These rules apply only while sign-in is on, because only then is the name the true one; with it off nothing changes.
- **Every refusal is in the audit log** as `auth.denied` with the user, the request and the reason ("needs the role approver", "acting as X"). The
  answer to the person says what role is missing.
- **Every field that names a person is checked.** `person` (the vault) was missing from the list of such fields; it is added, and a test now reads the
  request schemas of the app and fails when a new `*_by` or `person` field is not on the list.

## Not decided here

- Thresholds that need a second person (large sum, new supplier, red legal remark): plan day 26.
- Hiding buttons a role cannot use. The server refuses; the pages show its message.
- Per-customer or per-category access. Roles are for the whole app.
