"""Users, sign-in sessions and the switch that turns sign-in on.

With sign-in off the app works as before: a name typed at the top is only a label in the log. With
it on, every request needs a signed-in user and every logged name is that user (see middleware.py).
Passwords are scrypt hashes, sessions are random tokens of which only a hash is stored, repeated
wrong passwords lock the account for a while, and every sign-in, failure, password change and user
change is written to the audit log."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import passwords
from app.config import Settings
from app.models import AuditLog, AuthSession, User
from app.pipeline.service import PipelineError
from app.runtime import store

ROLES = {
    "admin": "users, settings and everything else",
    "buyer": "requests, suppliers, offers, quotes and orders",
    "approver": "approves letters, quotes, orders, invoices, bank changes and vault access",
    "legal": "reads and edits contracts and legal rules",
}
MAX_FAILURES = 5
LOCK_MINUTES = 15
GENERIC = "wrong name or password"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def _audit(session: Session, who: str, action: str, **payload) -> None:
    session.add(AuditLog(actor="human", actor_id=who, action=action, payload=payload))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def enabled(settings: Settings) -> bool:
    return bool(settings.auth_enabled) and not settings.auth_force_off


def public(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "roles": list(user.roles or []),
        "active": user.active,
        "locked": bool(user.locked_until and _aware(user.locked_until) > _now()),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_by": user.created_by,
    }


def users_exist(session: Session) -> bool:
    return session.scalar(select(func.count()).select_from(User)) > 0


def _clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if len(name) < 2 or len(name) > 128:
        raise ValueError("the name is 2 to 128 characters")
    return name


def _clean_roles(roles: list[str]) -> list[str]:
    out = [r for r in ROLES if r in set(roles or [])]
    unknown = set(roles or []) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown role: {', '.join(sorted(unknown))}; roles are {', '.join(ROLES)}")
    if not out:
        raise ValueError("give the user at least one role")
    return out


def _by_name(session: Session, name: str) -> User | None:
    return session.scalar(select(User).where(func.lower(User.name) == name.casefold()))


def _active_admins(session: Session) -> int:
    return sum(1 for u in session.scalars(select(User).where(User.active.is_(True))) if "admin" in u.roles)


def create_user(session: Session, name: str, password: str, roles: list[str], created_by: str) -> User:
    name, roles = _clean_name(name), _clean_roles(roles)
    if _by_name(session, name) is not None:
        raise PipelineError("a user with this name already exists")
    passwords.check_strength(password, name)
    user = User(
        name=name,
        password_hash=passwords.hash_password(password),
        roles=roles,
        created_by=created_by,
        password_changed_at=_now(),
    )
    session.add(user)
    session.flush()
    _audit(session, created_by, "auth.user_created", user=name, roles=roles)
    session.commit()
    return user


def bootstrap_admin(session: Session, name: str, password: str) -> User:
    """The first user, allowed only while there are none. It is an administrator."""
    if users_exist(session):
        raise PipelineError("users already exist: ask an administrator to add you")
    return create_user(session, name, password, ["admin"], created_by="(first user)")


def login(session: Session, settings: Settings, name: str, password: str) -> tuple[str, User]:
    user = _by_name(session, " ".join((name or "").split()))
    if user is None or not user.active:
        # same work and same message as a wrong password, so names cannot be probed
        passwords.verify_password(password or "", passwords.hash_password("x"))
        _audit(session, (name or "")[:128], "auth.login_failed", reason="unknown or inactive")
        session.commit()
        raise PermissionError(GENERIC)
    locked = _aware(user.locked_until)
    if locked and locked > _now():
        _audit(session, user.name, "auth.login_refused", reason="locked")
        session.commit()
        raise PermissionError("too many wrong passwords: try again in a few minutes")
    if not passwords.verify_password(password or "", user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILURES:
            user.locked_until, user.failed_logins = _now() + timedelta(minutes=LOCK_MINUTES), 0
        _audit(session, user.name, "auth.login_failed", reason="wrong password")
        session.commit()
        raise PermissionError(GENERIC)
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, _now()
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=_hash_token(token),
            user_id=user.id,
            expires_at=_now() + timedelta(hours=settings.auth_session_hours),
            last_seen_at=_now(),
        )
    )
    _audit(session, user.name, "auth.login")
    session.commit()
    return token, user


def user_from_token(session: Session, settings: Settings, token: str | None) -> User | None:
    if not token:
        return None
    row = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
    if row is None:
        return None
    now = _now()
    idle = timedelta(minutes=settings.auth_idle_minutes)
    user = session.get(User, row.user_id)
    if (
        _aware(row.expires_at) <= now
        or now - _aware(row.last_seen_at) > idle
        or user is None
        or not user.active
    ):
        session.delete(row)
        session.commit()
        return None
    if now - _aware(row.last_seen_at) > timedelta(minutes=1):
        row.last_seen_at = now
        session.commit()
    return user


def logout(session: Session, token: str | None) -> None:
    row = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash_token(token or "")))
    if row is not None:
        user = session.get(User, row.user_id)
        _audit(session, user.name if user else "?", "auth.logout")
        session.delete(row)
        session.commit()


def _revoke_sessions(session: Session, user_id: int, keep: str | None = None) -> None:
    for row in session.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
        if keep is None or row.token_hash != _hash_token(keep):
            session.delete(row)


def change_password(session: Session, user: User, old: str, new: str, token: str | None) -> None:
    if not passwords.verify_password(old or "", user.password_hash):
        _audit(session, user.name, "auth.password_change_refused")
        session.commit()
        raise PermissionError("the current password is wrong")
    passwords.check_strength(new, user.name)
    user.password_hash, user.password_changed_at = passwords.hash_password(new), _now()
    _revoke_sessions(session, user.id, keep=token)
    _audit(session, user.name, "auth.password_changed")
    session.commit()


def list_users(session: Session) -> list[dict]:
    return [public(u) for u in session.scalars(select(User).order_by(func.lower(User.name)))]


def update_user(
    session: Session, admin: User, user_id: int, roles: list[str] | None, active: bool | None
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise LookupError("user not found")
    before = {"roles": list(user.roles), "active": user.active}
    if roles is not None:
        user.roles = _clean_roles(roles)
    if active is not None:
        user.active = active
    if _active_admins(session) == 0:
        session.rollback()
        raise PipelineError("there must always be at least one active administrator")
    if not user.active:
        _revoke_sessions(session, user.id)
    _audit(
        session,
        admin.name,
        "auth.user_changed",
        user=user.name,
        before=before,
        after={"roles": list(user.roles), "active": user.active},
    )
    session.commit()
    return user


def reset_password(session: Session, admin: User, user_id: int, new: str) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise LookupError("user not found")
    passwords.check_strength(new, user.name)
    user.password_hash, user.password_changed_at = passwords.hash_password(new), _now()
    user.failed_logins, user.locked_until = 0, None
    _revoke_sessions(session, user.id)
    _audit(session, admin.name, "auth.password_reset", user=user.name)
    session.commit()


def set_enabled(session: Session, settings: Settings, admin: User, on: bool) -> None:
    if on and _active_admins(session) == 0:
        raise PipelineError("add an administrator first")
    store.save(session, settings, admin.name, {"auth_enabled": 1 if on else 0})
    store.apply(session, settings)
    _audit(session, admin.name, "auth.enabled" if on else "auth.disabled")
    session.commit()


def audit_events(session: Session, limit: int = 100) -> list[dict]:
    rows = session.scalars(
        select(AuditLog).where(AuditLog.action.like("auth.%")).order_by(AuditLog.id.desc()).limit(limit)
    )
    return [
        {
            "id": r.id,
            "at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            "who": r.actor_id,
            "action": r.action,
            "detail": r.payload,
        }
        for r in rows
    ]
