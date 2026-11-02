from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import middleware, rules, service
from app.config import Settings, get_settings
from app.db import get_session
from app.models import User
from app.pipeline.api import guarded

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    name: str = Field(max_length=128)
    password: str = Field(max_length=300)


class NewUserIn(BaseModel):
    name: str = Field(max_length=128)
    password: str = Field(max_length=300)
    roles: list[str]


class UserPatchIn(BaseModel):
    roles: list[str] | None = None
    active: bool | None = None


class PasswordIn(BaseModel):
    old: str = Field(max_length=300)
    new: str = Field(max_length=300)


class ResetIn(BaseModel):
    new: str = Field(max_length=300)


class EnableIn(BaseModel):
    enabled: bool


def _user(request: Request, session: Session, settings: Settings) -> User | None:
    return service.user_from_token(session, settings, middleware._token(request))


def _need_user(request: Request, session: Session, settings: Settings) -> User:
    user = _user(request, session, settings)
    if user is None:
        raise HTTPException(401, "sign in first")
    return user


def _need_admin(request: Request, session: Session, settings: Settings) -> User:
    user = _need_user(request, session, settings)
    if "admin" not in user.roles:
        raise HTTPException(403, "only an administrator can do this")
    return user


def _state(session: Session, settings: Settings, user: User | None) -> dict:
    return {
        "enabled": service.enabled(settings),
        "forced_off": bool(settings.auth_force_off and settings.auth_enabled),
        "users_exist": service.users_exist(session),
        "user": service.public(user) if user else None,
        "roles": service.ROLES,
    }


@router.get("/auth/state")
def auth_state(
    request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return _state(session, settings, _user(request, session, settings))


@router.post("/auth/bootstrap")
def bootstrap(
    body: NewUserIn,
    response: Response,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Creates the first user, an administrator, while there are none. Signs them in."""
    user = guarded(service.bootstrap_admin, session, body.name, body.password)
    return _sign_in(request, response, session, settings, user.name, body.password)


def _sign_in(request, response, session, settings, name, password):
    try:
        token, user = service.login(session, settings, name, password)
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        rules.COOKIE,
        token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )
    return _state(session, settings, user)


@router.post("/auth/login")
def login(
    body: LoginIn,
    response: Response,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return _sign_in(request, response, session, settings, body.name, body.password)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    service.logout(session, middleware._token(request))
    response.delete_cookie(rules.COOKIE, path="/")
    return _state(session, settings, None)


@router.post("/auth/password")
def change_password(
    body: PasswordIn,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user = _need_user(request, session, settings)
    try:
        guarded(service.change_password, session, user, body.old, body.new, middleware._token(request))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"ok": True}


@router.put("/auth/enabled")
def set_enabled(
    body: EnableIn,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Turns sign-in on or off. Needs a signed-in administrator, whichever mode is current."""
    admin = _need_admin(request, session, settings)
    guarded(service.set_enabled, session, settings, admin, body.enabled)
    fresh = (request.app.dependency_overrides.get(get_settings) or get_settings)()
    return _state(session, fresh, admin)


@router.get("/users")
def users(
    request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    _need_admin(request, session, settings)
    return {
        "users": service.list_users(session),
        "roles": service.ROLES,
        "events": service.audit_events(session),
    }


@router.post("/users")
def create_user(
    body: NewUserIn,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    admin = _need_admin(request, session, settings)
    guarded(service.create_user, session, body.name, body.password, body.roles, admin.name)
    return service.list_users(session)


@router.patch("/users/{user_id}")
def patch_user(
    user_id: int,
    body: UserPatchIn,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    admin = _need_admin(request, session, settings)
    guarded(service.update_user, session, admin, user_id, body.roles, body.active)
    return service.list_users(session)


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    body: ResetIn,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    admin = _need_admin(request, session, settings)
    guarded(service.reset_password, session, admin, user_id, body.new)
    return {"ok": True}
