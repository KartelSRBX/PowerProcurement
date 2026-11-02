"""What the middleware checks: which paths are open without signing in, which request fields name the
person doing the action, and which role each kind of request needs."""

import re

COOKIE = "pp_session"

# Reachable without signing in, even when sign-in is on.
PUBLIC = (
    ("GET", re.compile(r"^/health(/ready)?$")),
    ("GET", re.compile(r"^/auth/state$")),
    ("POST", re.compile(r"^/auth/login$")),
    ("POST", re.compile(r"^/auth/bootstrap$")),
)

# Request fields (JSON body, form field or query parameter) that carry the name of the person acting.
# When sign-in is on each must be the signed-in user's name, so nobody acts under somebody else's name.
ACTOR_FIELDS = frozenset(
    {
        "by", "changed_by", "confirmed_by", "entered_by", "decided_by", "set_by", "removed_by", "checked_by",
        "approved_by", "saved_by", "reviewed_by", "requested_by", "proposed_by", "imported_by", "created_by",
        "cleared_by", "callback_by", "sent_by", "updated_by", "loaded_by", "drafted_by", "person",
    }
)  # fmt: skip


def is_public(method: str, path: str) -> bool:
    return any(m == method and rx.match(path) for m, rx in PUBLIC)


# --- Roles ------------------------------------------------------------------------------------------
# Who may do what once sign-in is on. A user has one or more roles and may do what any of them allows.
# An administrator may do everything. The first rule that matches a request decides; None means any
# signed-in user. A request that matches no rule needs an administrator (fail closed), and a test makes
# sure no route of the app falls through to that.

ANY = None
APPROVER = frozenset({"approver"})
BUYER = frozenset({"buyer"})
LEGAL = frozenset({"legal"})
ADMIN = frozenset()  # nobody but an administrator
BUYER_OR_APPROVER = frozenset({"buyer", "approver"})
LEGAL_READERS = frozenset({"legal", "approver"})

_MUTATING = ("POST", "PUT", "PATCH", "DELETE")
_ALL = ("GET", "HEAD", *_MUTATING)

# Approvals: the decisions that let something go out or be paid. Only an approver (or an administrator).
_APPROVALS = (
    r"^/(rfqs|quotes|letters)/\d+/decision$|^/requests/\d+/orders$|^/orders/\d+/supplier-invoice/accept$"
)
_APPROVALS += r"|^/bank-proposals/\d+/decision$|^/vault/requests/\d+/decide$"

# Buyer work: everything that moves a request, a supplier or an order along.
_BUYER_AREAS = "|".join(
    ("requests", "suppliers", "offers", "orders", "quotes", "replies", "rfqs", "letters", "mail")
    + ("articles", "screenings", "bank-proposals", "tasks")
)

RULES: list[tuple[tuple[str, ...], re.Pattern, frozenset | None]] = [
    (_ALL, re.compile(r"^/(auth|users)(/|$)"), ANY),  # these check the user themselves
    (_MUTATING, re.compile(_APPROVALS), APPROVER),
    # administration
    (_MUTATING, re.compile(r"^/(settings|duties|analytics/demo-history|mail/demo-load)(/|$)"), ADMIN),
    (_MUTATING, re.compile(r"^/legal/settings$"), ADMIN),
    (_MUTATING, re.compile(r"^/tasks/(config|webhook)$"), ADMIN),
    (_MUTATING, re.compile(r"^/vault$|^/vault/\d+$"), ADMIN),  # adding, editing, removing entries
    # reading
    (("GET", "HEAD"), re.compile(r"^/legal(/|$)"), LEGAL_READERS),
    (("GET", "HEAD"), re.compile(r"^/vault(/|$)"), BUYER_OR_APPROVER),
    (("GET", "HEAD"), re.compile(r"^/"), ANY),
    # contracts and legal rules
    (_MUTATING, re.compile(r"^/legal(/|$)"), LEGAL),
    # the vault: asking for access, opening it, revealing what was approved
    (_MUTATING, re.compile(r"^/vault/(open|\d+/requests|requests/\d+/reveal)$"), BUYER_OR_APPROVER),
    # calculations that change nothing
    (_MUTATING, re.compile(r"^/pricing/landed$"), ANY),
    (_MUTATING, re.compile(r"^/analytics/narrative$"), BUYER_OR_APPROVER),
    (_MUTATING, re.compile(rf"^/({_BUYER_AREAS})(/|$)"), BUYER),
]


def required_roles(method: str, path: str) -> tuple[frozenset | None, bool]:
    """(roles that may do it, whether a rule names the request). None means any signed-in user; an
    empty set means administrators only."""
    for methods, rx, roles in RULES:
        if method in methods and rx.match(path):
            return roles, True
    return ADMIN, False


def allowed(roles: list[str], method: str, path: str) -> bool:
    need, _ = required_roles(method, path)
    return need is None or "admin" in roles or bool(set(roles) & need)


def describe(method: str, path: str) -> str:
    need, _ = required_roles(method, path)
    return "an administrator" if not need else "the role " + " or ".join(sorted(need))
