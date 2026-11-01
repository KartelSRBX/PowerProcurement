# 0020. Supplier bank details: a proposal, a call, a second person

Status: accepted (plan day 19)

## Context

The usual payment fraud is a mail that says "our account has changed". The defence is a procedure, not a check the code can do:
confirm the change by calling a number you already trusted, and let a second person look before money moves. The app has the same
shape for access credentials (0009); the bank account follows it.

## Decisions

- **Every set of an account, the first one included, is a proposal.** One person proposes it together with a record of the call: who
  at the supplier confirmed, who made the call, on which date (not in the future), and **where the number called came from**:
  the contract, an earlier verified record, the supplier's official website, or another source that must be explained. The mail that
  announced the change is not among the choices. A different person approves or rejects; until then the old account stays in force.
- **Different means a different name,** compared trimmed and ignoring case. Rejecting needs a comment. The proposer can withdraw;
  nobody else can (they can reject). One proposal per supplier at a time.
- **The account is stored encrypted** with the same key as the vault and the Settings secrets, and a SHA-256 of the account (letters
  and digits, upper case) is kept beside it so that the same account on two suppliers can be found without decrypting anything.
  The warning for that is shown when it is proposed; the finder over all suppliers comes on day 20.
- **The code checks form and warns; it never blocks on a guess.** An IBAN must pass the mod-97 check (a typing error is refused);
  anything else must be a domestic number of digits and dashes, 8 to 24 long, and is accepted as typed (no per-country rules are
  invented). A beneficiary name is required. Warnings shown to the approver: the IBAN country differs from the supplier's country,
  the holder does not resemble the supplier's name, the account is already used by another supplier.
- **A recent change is shown where the money goes.** The order panel has a "Pays to" line with the account in force and a warning
  for 30 days after a change. A missing account is shown as missing.
- **Every step is in the audit log** (`bank.proposed`, `bank.approved`, `bank.rejected`, `bank.withdrawn`) with the names, never the account.

## Not decided here

- This is a process aid, not a lock: without sign-in the app knows only the name a person typed, so two people at one keyboard can
  satisfy it. Sign-in and roles come on days 24 to 25; making a second person mandatory by risk comes on days 26 to 27.
- Reading the account out of a mail or an invoice. Nothing here does it, on purpose.
