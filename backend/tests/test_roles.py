"""Roles in action: with sign-in on, each kind of request needs a role, an approver is not the author of
what they approve, and every refusal is in the audit log with the user."""

import re

import pytest

from app import config
from app.auth import rules
from app.config import get_settings, set_overrides
from app.main import app
from app.models import AuditLog
from tests.test_auth import _add, _first, _login, _on
from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401


@pytest.fixture
def c(client):  # noqa: F811
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    yield client
    set_overrides({})


def _as(c, name):
    c.post("/auth/logout")
    assert _login(c, name).status_code == 200


def _team(c):
    _first(c)
    for name, roles in [
        ("Bob Buyer", ["buyer"]),
        ("Ann Approver", ["approver"]),
        ("Lee Legal", ["legal"]),
        ("Dual Dan", ["buyer", "approver"]),
        ("Eve Approver", ["approver"]),
    ]:
        _add(c, name, roles)


def _mutating_routes():
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                yield method.upper(), re.sub(r"\{[^}]+\}", "1", path)


def test_every_route_of_the_app_has_a_role_rule():
    # A new route that no rule names would silently need an administrator: make that a decision, not luck.
    unnamed = [(m, p) for m, p in _mutating_routes() if not rules.required_roles(m, p)[1]]
    assert unnamed == []


def test_every_field_that_names_a_person_is_checked_against_the_signed_in_user():
    # needed_by and respond_by are dates, not people.
    people = set()
    for schema in app.openapi()["components"]["schemas"].values():
        for field in schema.get("properties") or {}:
            if (field.endswith("_by") and field not in ("needed_by", "respond_by")) or field == "person":
                people.add(field)
    assert people - rules.ACTOR_FIELDS == set()


@pytest.mark.parametrize(
    ("roles", "method", "path", "ok"),
    [
        (["buyer"], "POST", "/requests/1/rfqs/draft", True),
        (["buyer"], "POST", "/rfqs/1/decision", False),
        (["buyer"], "POST", "/requests/1/orders", False),
        (["approver"], "POST", "/rfqs/1/decision", True),
        (["approver"], "POST", "/orders/1/supplier-invoice/accept", True),
        (["approver"], "POST", "/requests/1/second-approval", True),
        (["buyer"], "POST", "/requests/1/second-approval", False),
        (["approver"], "POST", "/suppliers", False),
        (["approver"], "GET", "/suppliers", True),
        (["legal"], "POST", "/legal/contracts", True),
        (["legal"], "POST", "/requests/manual", False),
        (["legal"], "GET", "/legal/contracts", True),
        (["buyer"], "GET", "/legal/contracts", False),
        (["approver"], "GET", "/legal/contracts", True),
        (["buyer"], "PUT", "/settings/ai", False),
        (["buyer"], "POST", "/vault", False),
        (["buyer"], "POST", "/vault/1/requests", True),
        (["legal"], "POST", "/vault/1/requests", False),
        (["buyer", "approver"], "POST", "/rfqs/1/decision", True),
        (["admin"], "PUT", "/settings/ai", True),
        (["admin"], "POST", "/legal/contracts", True),
        (["buyer"], "POST", "/pricing/landed", True),
        (["buyer"], "POST", "/something/new", False),  # nothing names it: administrators only
        (["admin"], "POST", "/something/new", True),
    ],
)
def test_the_role_table(roles, method, path, ok):
    assert rules.allowed(roles, method, path) is ok


def test_with_sign_in_off_roles_do_not_matter(c):
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    assert c.post(f"/requests/{rid}/rfqs/draft").status_code == 200
    assert c.put("/settings/urgency", json={"changed_by": "x"}).status_code != 403


def test_each_role_can_do_its_work_and_not_the_work_of_others(c):
    _team(c)
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    _on(c)

    _as(c, "Bob Buyer")
    assert c.get("/suppliers").status_code == 200
    r = c.post(f"/rfqs/{drafts[0]['id']}/decision", json={"approve": True, "decided_by": "Bob Buyer"})
    assert r.status_code == 403 and "role approver" in r.json()["detail"]
    assert c.put("/settings/urgency", json={"changed_by": "Bob Buyer"}).status_code == 403
    assert c.get("/legal/contracts").status_code == 403
    assert c.get("/users").status_code == 403

    _as(c, "Ann Approver")
    assert c.get("/suppliers").status_code == 200 and c.get("/legal/contracts").status_code == 200
    r = c.post(f"/rfqs/{drafts[0]['id']}/decision", json={"approve": True, "decided_by": "Ann Approver"})
    assert r.status_code == 200 and r.json()["status"] == "sent"
    r = c.post("/suppliers", json={"name": "X", "country": "RS", "changed_by": "Ann Approver"})
    assert r.status_code == 403 and "role buyer" in r.json()["detail"]

    _as(c, "Lee Legal")
    assert c.get("/legal/contracts").status_code == 200
    assert c.post(f"/requests/{rid}/score").status_code == 403
    assert c.post("/legal/contracts", json={}).status_code != 403  # reaches the route (422), not refused

    _as(c, "Dual Dan")  # two roles: the union
    r = c.post(f"/rfqs/{drafts[1]['id']}/decision", json={"approve": False, "decided_by": "Dual Dan"})
    assert r.status_code == 200 and c.post(f"/requests/{rid}/score").status_code != 403

    _as(c, "Admin Anna")
    assert c.get("/users").status_code == 200 and c.get("/legal/contracts").status_code == 200
    assert c.put("/settings/urgency", json={"changed_by": "Admin Anna"}).status_code != 403


def test_refusals_are_in_the_audit_log_with_the_user_and_the_reason(c):
    _team(c)
    _on(c)
    _as(c, "Bob Buyer")
    assert c.post("/rfqs/1/decision", json={"approve": True, "decided_by": "Bob Buyer"}).status_code == 403
    assert c.put("/requests/1/urgency", json={"changed_by": "Eve", "urgent": True}).status_code == 403
    rows = c.session.query(AuditLog).filter(AuditLog.action == "auth.denied").all()
    assert {(r.actor_id, r.payload["path"]) for r in rows} == {
        ("Bob Buyer", "/rfqs/1/decision"),
        ("Bob Buyer", "/requests/1/urgency"),
    }
    assert any("needs the role approver" in r.payload["why"] for r in rows)
    assert any("acting as 'Eve'" in r.payload["why"] for r in rows)


def test_the_approver_is_not_the_author_of_what_they_approve(c):
    _team(c)
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    drafts = c.post(f"/requests/{rid}/rfqs/draft").json()
    _on(c)

    _as(c, "Dual Dan")
    rfq = drafts[0]["id"]
    assert c.patch(f"/rfqs/{rfq}", json={"body": "my wording"}).json()["edited_by"] == "Dual Dan"
    r = c.post(f"/rfqs/{rfq}/decision", json={"approve": True, "decided_by": "Dual Dan"})
    assert r.status_code == 409 and "different person" in r.json()["detail"]
    # a draft nobody edited can be approved by anyone with the role, and so can an edited one by someone else
    other = drafts[1]["id"]
    assert (
        c.post(f"/rfqs/{other}/decision", json={"approve": False, "decided_by": "Dual Dan"}).status_code
        == 200
    )
    _as(c, "Eve Approver")
    r = c.post(f"/rfqs/{rfq}/decision", json={"approve": True, "decided_by": "Eve Approver"})
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert c.session.query(AuditLog).filter(AuditLog.action == "auth.denied").count() == 0
