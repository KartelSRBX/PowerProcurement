# 0025. Sign-in: users, sessions and the switch

Status: accepted (plan day 24)

## Context

Until now the name typed at the top was only a label: anyone who could open the app could act under any name, so "a named person approved this" and
"a different person approved this" (the bank change, the vault, the invoice) meant nothing against someone who wanted to cheat. Several
earlier decisions (0009, 0020) say so and name this day as the fix.

## Decisions

- **Two modes, one switch.** Sign-in is **off** by default and everything works as before. An administrator turns it **on** in Settings; from then on
  every request needs a signed-in user. Turning it on needs a signed-in administrator and at least one active administrator; turning it off is logged.
  If nobody can get in, the server environment variable `AUTH_FORCE_OFF=true` switches it off again (anyone who controls the environment controls the
  database anyway).
- **The first user is an administrator and is created while there are no users**, from Settings. After that only an administrator adds users. A user
  has a unique name (compared without regard to case), a password and one or more roles. Roles are stored now and enforced from day 25.
- **The name stays the key.** The endpoints still receive the person's name in the request, as before. With sign-in on, the middleware checks that every
  field that names the acting person (`changed_by`, `approved_by`, `decided_by`, `by` and the others, in the body or the query) is the signed-in
  user's name, and answers 403 otherwise. So no route changed, every log line already holds the user, and nobody can act under another name. A request
  with a form body is refused (415) while sign-in is on, because no route reads forms and a name in one would go unchecked.
- **Passwords** are hashed with scrypt from the standard library, salted, with the parameters stored in the hash. Ten characters at least; no rules about
  mixing character kinds. Five wrong passwords lock the account for 15 minutes. A wrong name and a wrong password give the same message and cost the same.
- **Sessions** are random 256-bit tokens in an HttpOnly, SameSite=Strict cookie (Secure over HTTPS); only a hash is stored. A session ends after 12 hours
  or 2 hours without use, on sign-out, when the password is changed or reset (other sessions), or when the user is deactivated. The browser holds no token
  it can read, and downloads work because the cookie goes with them. A script can send the same token as a bearer header.
- **Every sign-in, failure, refusal, password change, user change, switch and denied action is in the audit log** with the name, never a password.
  Administrators see recent events in Settings.
- **There is always an active administrator.** The last one cannot be deactivated or lose the role.

## Not decided here

- Roles in action: who may do what (day 25).
- Passwords by email, single sign-on, two-factor codes. A small team on one server does not need them yet; a password reset is done by an administrator.
- Rate limiting by address. The lock is per account.
- Session lifetime settings in the interface; they are environment values (`AUTH_SESSION_HOURS`, `AUTH_IDLE_MINUTES`).
