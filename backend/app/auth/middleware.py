"""When sign-in is on, every request must carry a valid session, and every field that names the acting
person must be the signed-in user. Nothing else in the app changes: the endpoints still receive the
name in the request as before, the middleware only makes sure it is the true one. With sign-in off
the middleware does nothing."""

import inspect
import json
from urllib.parse import parse_qsl

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth import rules, service
from app.config import get_settings
from app.db import get_session


async def _body(receive) -> bytes:
    chunks, more = [], True
    while more:
        msg = await receive()
        if msg["type"] == "http.disconnect":
            break
        chunks.append(msg.get("body", b""))
        more = msg.get("more_body", False)
    return b"".join(chunks)


def _replay(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def _token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(rules.COOKIE)


def _open_session(app):
    """A session the way the routes get theirs, including a test's override."""
    factory = app.dependency_overrides.get(get_session, get_session)
    made = factory()
    if inspect.isgenerator(made):
        return next(made), made.close
    return made, lambda: None


def _lookup(app, settings, token):
    session, close = _open_session(app)
    try:
        user = service.user_from_token(session, settings, token)
        if user is None:
            return None
        return {"id": user.id, "name": user.name, "roles": list(user.roles or [])}
    finally:
        close()


def _denied(app, who: str, method: str, path: str, why: str) -> None:
    session, close = _open_session(app)
    try:
        service._audit(session, who, "auth.denied", method=method, path=path, why=why)
        session.commit()
    finally:
        close()


def _foreign_names(fields: dict, name: str) -> list[str]:
    return [
        str(v)
        for k, v in fields.items()
        if k in rules.ACTOR_FIELDS and isinstance(v, str) and v.strip().casefold() != name.casefold()
    ]


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        app = scope["app"]
        settings = (app.dependency_overrides.get(get_settings) or get_settings)()
        if not service.enabled(settings):
            return await self.app(scope, receive, send)

        method, path = scope["method"], scope["path"]
        if method == "OPTIONS" or rules.is_public(method, path):
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        user = await run_in_threadpool(_lookup, app, settings, _token(request))
        if user is None:
            return await JSONResponse({"detail": "sign in first"}, status_code=401)(scope, receive, send)
        scope["auth_user"] = user

        fields = dict(parse_qsl(scope.get("query_string", b"").decode()))
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            raw = await _body(receive)
            receive = _replay(raw)
            ctype = request.headers.get("content-type", "")
            if "json" in ctype and raw:
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = None
                if isinstance(data, dict):
                    fields.update(data)
            elif "multipart/form-data" in ctype or "x-www-form-urlencoded" in ctype:
                # No route reads forms today. Refuse them rather than let a name in one go unchecked.
                msg = "send JSON: form bodies are not accepted while sign-in is on"
                return await JSONResponse({"detail": msg}, status_code=415)(scope, receive, send)
        wrong = _foreign_names(fields, user["name"])
        if wrong:
            await run_in_threadpool(_denied, app, user["name"], method, path, f"acting as {wrong[0]!r}")
            msg = f"you are signed in as {user['name']!r}: the action cannot be recorded under {wrong[0]!r}"
            return await JSONResponse({"detail": msg}, status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)
