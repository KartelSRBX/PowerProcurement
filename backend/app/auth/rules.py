"""What the middleware checks: which paths are open without signing in, and which request fields name
the person doing the action."""

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
        "cleared_by", "callback_by", "sent_by", "updated_by", "loaded_by", "drafted_by",
    }
)  # fmt: skip


def is_public(method: str, path: str) -> bool:
    return any(m == method and rx.match(path) for m, rx in PUBLIC)
