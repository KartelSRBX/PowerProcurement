"""Sign-in: users with scrypt-hashed passwords, sessions, a lock after repeated failures, and a switch that
makes every request need a signed-in user, whose name is the only one any action can be recorded under."""

from datetime import timedelta

import pytest

from app import config
from app.auth import passwords, service
from app.config import get_settings, set_overrides
from app.main import app
from app.models import AuditLog, AuthSession, User
from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401

PW = "correct horse battery"


@pytest.fixture
def c(client):  # noqa: F811
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    yield client
    set_overrides({})


def _first(c, name="Admin Anna", password=PW):
    r = c.post("/auth/bootstrap", json={"name": name, "password": password, "roles": ["admin"]})
    assert r.status_code == 200, r.text
    return r.json()


def _login(c, name, password=PW):
    return c.post("/auth/login", json={"name": name, "password": password})


def _add(c, name, roles=("buyer",), password=PW):
    r = c.post("/users", json={"name": name, "password": password, "roles": list(roles)})
    assert r.status_code == 200, r.text
    return r.json()


def _on(c):
    r = c.put("/auth/enabled", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True


def test_passwords_are_hashed_with_scrypt_and_checked(c):
    h = passwords.hash_password(PW)
    assert h.startswith("scrypt$") and PW not in h and h != passwords.hash_password(PW)  # salted
    assert passwords.verify_password(PW, h) and not passwords.verify_password(PW + "x", h)
    assert not passwords.verify_password(PW, "garbage") and not passwords.verify_password(PW, "md5$1$2$3$4$5")
    for bad in ("short", "x" * 201, "aaaaaaaaaaaa"):
        with pytest.raises(ValueError):
            passwords.check_strength(bad)
    with pytest.raises(ValueError, match="same as the name"):
        passwords.check_strength("Admin Anna", "admin anna")


def test_the_first_user_is_an_administrator_and_there_is_only_one_first_user(c):
    s = c.get("/auth/state").json()
    assert s == {
        "enabled": False,
        "forced_off": False,
        "users_exist": False,
        "user": None,
        "roles": s["roles"],
    }
    me = _first(c)
    assert me["user"]["name"] == "Admin Anna" and me["user"]["roles"] == ["admin"] and me["users_exist"]
    row = c.session.query(User).one()
    assert PW not in row.password_hash and row.password_hash.startswith("scrypt$")
    assert c.post("/auth/bootstrap", json={"name": "Eve", "password": PW, "roles": []}).status_code == 409
    assert c.get("/auth/state").json()["user"]["name"] == "Admin Anna"  # the cookie from bootstrap


def test_nothing_changes_while_sign_in_is_off(c):
    assert c.get("/requests").status_code == 200
    rid = new_request(c)
    assert (
        c.put(f"/requests/{rid}/urgency", json={"changed_by": "whoever", "urgent": True}).status_code == 200
    )


def test_only_an_administrator_can_turn_sign_in_on_or_manage_users(c):
    assert c.put("/auth/enabled", json={"enabled": True}).status_code == 401
    assert c.get("/users").status_code == 401
    _first(c)
    _add(c, "Bob Buyer")
    c.post("/auth/logout")
    assert _login(c, "Bob Buyer").status_code == 200
    assert (
        c.get("/users").status_code == 403
        and c.put("/auth/enabled", json={"enabled": True}).status_code == 403
    )
    assert c.post("/users", json={"name": "Mallory", "password": PW, "roles": ["admin"]}).status_code == 403


def test_with_sign_in_on_every_request_needs_a_session(c):
    _first(c)
    _on(c)
    c.post("/auth/logout")
    assert c.get("/requests").status_code == 401 and c.get("/suppliers").status_code == 401
    assert c.post("/requests/manual", json={}).status_code == 401
    assert c.get("/health").status_code == 200 and c.get("/auth/state").json()["enabled"] is True
    assert _login(c, "Admin Anna").status_code == 200
    assert c.get("/requests").status_code == 200
    # the same token works as a bearer header for scripts, and a bad one does not
    token = c.cookies.get("pp_session")
    c.cookies.clear()
    assert c.get("/requests", headers={"authorization": f"Bearer {token}"}).status_code == 200
    assert c.get("/requests", headers={"authorization": "Bearer nonsense"}).status_code == 401


def test_a_signed_in_user_can_only_act_under_their_own_name(c):
    _first(c)
    rid = new_request(c)
    _on(c)
    url = f"/requests/{rid}/urgency"
    ok = c.put(url, json={"changed_by": "admin anna", "urgent": True})  # case does not matter
    assert ok.status_code == 200
    bad = c.put(url, json={"changed_by": "Somebody Else", "urgent": True})
    assert bad.status_code == 403 and "signed in as 'Admin Anna'" in bad.json()["detail"]
    assert c.put(url, json={"changed_by": " ", "urgent": True}).status_code == 403
    # a query parameter naming the person is checked too
    assert c.delete("/screenings/1", params={"removed_by": "Somebody Else"}).status_code == 403
    denied = c.session.query(AuditLog).filter_by(action="auth.denied").all()
    assert len(denied) == 3 and denied[0].actor_id == "Admin Anna"
    # an action that names nobody goes through to the route, which decides
    assert c.get(url).status_code == 200


def test_form_bodies_are_refused_while_sign_in_is_on(c):
    _first(c)
    _on(c)
    r = c.post("/mail/1/attach", data={"by": "Somebody Else"}, files={"f": ("a.txt", b"x")})
    assert r.status_code == 415


def test_wrong_passwords_are_refused_the_same_way_and_lock_the_account(c):
    _first(c)
    assert _login(c, "Nobody", PW).json()["detail"] == "wrong name or password"
    assert _login(c, "Admin Anna", "wrong password!").json()["detail"] == "wrong name or password"
    for _ in range(service.MAX_FAILURES - 1):
        _login(c, "Admin Anna", "wrong password!")
    locked = _login(c, "Admin Anna", PW)  # even the right one is refused while locked
    assert locked.status_code == 401 and "too many wrong passwords" in locked.json()["detail"]
    user = c.session.query(User).one()
    user.locked_until = service._now() - timedelta(minutes=1)
    c.session.commit()
    assert _login(c, "Admin Anna", PW).status_code == 200 and c.session.query(User).one().failed_logins == 0
    actions = [a.action for a in c.session.query(AuditLog).filter(AuditLog.action.like("auth.login%"))]
    assert "auth.login_failed" in actions and "auth.login_refused" in actions and "auth.login" in actions
    assert "wrong password!" not in str([a.payload for a in c.session.query(AuditLog)])


def test_sessions_expire_when_idle_or_old_and_logout_ends_them(c):
    _first(c)
    _on(c)
    assert c.get("/requests").status_code == 200
    row = c.session.query(AuthSession).one()
    token_hash = row.token_hash
    assert token_hash != c.cookies.get("pp_session") and len(token_hash) == 64  # only a hash is stored
    row.last_seen_at = service._now() - timedelta(minutes=SETTINGS.auth_idle_minutes + 1)
    c.session.commit()
    assert c.get("/requests").status_code == 401 and c.session.query(AuthSession).count() == 0
    _login(c, "Admin Anna")
    row = c.session.query(AuthSession).one()
    row.expires_at = service._now() - timedelta(seconds=1)
    c.session.commit()
    assert c.get("/requests").status_code == 401
    _login(c, "Admin Anna")
    assert c.post("/auth/logout").status_code == 200 and c.get("/requests").status_code == 401


def test_changing_and_resetting_passwords_ends_other_sessions(c):
    _first(c)
    _add(c, "Bob Buyer")
    bob = next(u for u in c.get("/users").json()["users"] if u["name"] == "Bob Buyer")["id"]
    c.post("/auth/logout")
    _login(c, "Bob Buyer")
    assert (
        c.post("/auth/password", json={"old": "nope nope nope", "new": "a brand new secret"}).status_code
        == 403
    )
    assert c.post("/auth/password", json={"old": PW, "new": "short"}).status_code == 422
    assert c.post("/auth/password", json={"old": PW, "new": "a brand new secret"}).status_code == 200
    c.post("/auth/logout")
    assert _login(c, "Bob Buyer", PW).status_code == 401
    assert _login(c, "Bob Buyer", "a brand new secret").status_code == 200
    token = c.cookies.get("pp_session")
    c.cookies.clear()
    _login(c, "Admin Anna")
    assert c.post(f"/users/{bob}/password", json={"new": "reset by the admin"}).status_code == 200
    c.cookies.clear()
    c.headers["authorization"] = f"Bearer {token}"
    try:
        assert c.get("/auth/state").json()["user"] is None  # Bob's old session was ended by the reset
    finally:
        del c.headers["authorization"]
    assert _login(c, "Bob Buyer", "reset by the admin").status_code == 200


def test_there_is_always_an_active_administrator_and_a_deactivated_user_is_signed_out(c):
    _first(c)
    _add(c, "Bob Buyer")
    users = c.get("/users").json()["users"]
    anna = next(u for u in users if u["name"] == "Admin Anna")["id"]
    bob = next(u for u in users if u["name"] == "Bob Buyer")["id"]
    assert c.patch(f"/users/{anna}", json={"active": False}).status_code == 409
    assert c.patch(f"/users/{anna}", json={"roles": ["buyer"]}).status_code == 409
    assert c.patch(f"/users/{bob}", json={"roles": ["wizard"]}).status_code == 422
    assert c.patch(f"/users/{bob}", json={"roles": []}).status_code == 422
    c.cookies.clear()
    _login(c, "Bob Buyer")
    bob_cookie = c.cookies.get("pp_session")
    c.cookies.clear()
    _login(c, "Admin Anna")
    assert c.patch(f"/users/{bob}", json={"active": False}).status_code == 200
    c.cookies.clear()
    c.cookies.set("pp_session", bob_cookie)
    assert c.get("/auth/state").json()["user"] is None
    assert _login(c, "Bob Buyer").status_code == 401


def test_user_names_are_unique_whatever_the_case_and_passwords_must_be_strong(c):
    _first(c)
    assert (
        c.post("/users", json={"name": "ADMIN ANNA", "password": PW, "roles": ["buyer"]}).status_code == 409
    )
    assert c.post("/users", json={"name": "X", "password": PW, "roles": ["buyer"]}).status_code == 422
    assert c.post("/users", json={"name": "Carl", "password": "weak", "roles": ["buyer"]}).status_code == 422
    assert c.post("/users", json={"name": "Carl", "password": PW, "roles": ["buyer"]}).status_code == 200


def test_the_environment_can_switch_sign_in_off_when_nobody_can_get_in(c):
    _first(c)
    _on(c)
    c.post("/auth/logout")
    assert c.get("/requests").status_code == 401
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(
        update={**config._overrides, "auth_force_off": True}
    )
    assert c.get("/requests").status_code == 200
    assert c.get("/auth/state").json()["forced_off"] is True


def test_turning_it_on_and_off_is_logged(c):
    _first(c)
    _on(c)
    assert c.put("/auth/enabled", json={"enabled": False}).status_code == 200
    assert c.get("/auth/state").json()["enabled"] is False
    events = c.get("/users").json()["events"]
    kinds = [e["action"] for e in events]
    assert "auth.enabled" in kinds and "auth.disabled" in kinds and "auth.user_created" in kinds
