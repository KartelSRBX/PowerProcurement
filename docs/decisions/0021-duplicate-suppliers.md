# 0021. Duplicate supplier finder

Status: accepted (plan day 20)

## Context

The same company entered twice splits its history (deliveries, prices, invoices) and, worse, can hide a payment to a bank account that
another record says belongs to someone else. Finding such pairs is a matching job; deciding that two records are one company is a
judgement.

## Decisions

- **Three signals, listed for a person.** The same tax number, the same bank account, and the same name once case, punctuation and legal
  forms (GmbH, d.o.o., Ltd and so on) are ignored, or a name that is very similar (similarity 0.9 or more on the cleaned names). A pair
  shows every reason it was found, strongest first: tax number and bank account, then name.
- **The tax number is a new optional profile field, typed by a person.** It is compared without spaces, dots and dashes and without a
  two-letter country prefix, and only when at least 5 characters remain. The same number in two countries is still listed, with a note
  saying the countries differ, because a number can be reused across registers and only a person can tell.
- **The bank account is compared by its hash** (0020), so nothing is decrypted and the list never carries an account. Accounts in force
  and accounts still waiting for a second person both count: a proposal that points at another supplier's account is exactly the case to see.
- **No merging, no blocking, no score effect.** The code does not join records, hide a supplier or change a ranking. A person records
  a verdict for the pair, *different companies* or *the same company*, with a reason; both go to the audit log. A "same" pair stays on the
  list so someone can act on it; merging is done by hand because the history on both sides decides which record survives.
- **A dismissal remembers what it saw.** The signals present at review time are stored; if a pair marked "different" later gains a new
  signal (say both now carry the same tax number), it comes back marked as such. A review can be removed.
- **Shown where it matters:** a list on the Suppliers tab, a warning at the top of a supplier's profile, and the list of possible duplicates
  returned when a supplier is created. Creating is never refused for it.

## Not decided here

- Matching on email domain, website or address: free-mail domains and shared addresses would produce noise, and the plan names three signals.
- Merging two supplier records. It needs a rule for orders, offers, price lines and bank history, and a second person.
- Checking a tax number against a register; no register is loaded.
