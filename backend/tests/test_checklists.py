"""The draft CBAM and Serbian e-invoicing checklists: every line has a source, a check date and a basis
for its date, and a person's answer on a line is recorded with their name."""

from datetime import date
from urllib.parse import urlparse

from app.auth import rules
from app.checklists.items import AREAS, BASES, CHECKED_ON, ITEMS, STATES
from app.models import AuditLog, ChecklistProgress
from tests.test_pipeline_e2e import client  # noqa: F401


def test_every_line_has_a_source_a_check_date_and_a_draft_status():
    assert len({i["key"] for i in ITEMS}) == len(ITEMS)
    for i in ITEMS:
        assert i["area"] in AREAS and i["status"] == "draft", i["key"]
        assert urlparse(i["source_url"]).scheme == "https" and i["source_kind"] in ("primary", "secondary"), (
            i["key"]
        )
        assert i["quote"].strip() and i["title"].strip() and i["detail"].strip(), i["key"]
        assert date.fromisoformat(i["checked_on"]) == date.fromisoformat(CHECKED_ON)
        assert i["date_basis"] in BASES, i["key"]


def test_a_date_that_is_not_from_a_primary_source_says_so():
    for i in ITEMS:
        if i["date"] is None:
            assert i["date_basis"] == "none", i["key"]
        elif i["date_basis"] == "primary":
            assert i["source_kind"] == "primary", i["key"]  # a primary basis needs a primary source
        else:
            assert i["date_basis"] in ("secondary", "inferred"), i["key"]
    # a date worked out from a rule, rather than stated, is never presented as a plain fact
    inferred = [i for i in ITEMS if i["date_basis"] == "inferred"]
    assert inferred and all(i["ask"] for i in inferred)


def test_the_list_marks_dates_that_need_checking(client):  # noqa: F811
    d = client.get("/checklists").json()
    assert d["checked_on"] == CHECKED_ON and "not legal advice" in d["note"]
    items = [i for a in d["areas"] for i in a["items"]]
    assert {a["key"] for a in d["areas"]} == set(AREAS) and len(items) == len(ITEMS)
    by = {i["key"]: i for i in items}
    assert (
        by["cbam-declaration"]["date_marked"] is True and by["cbam-declaration"]["date_basis"] == "inferred"
    )
    assert by["sef-law-2025"]["date_marked"] is False  # its date is in a primary source
    assert by["sef-foreign"]["date"] is None and by["sef-foreign"]["ask"]
    assert all(a["answered"] == 0 for a in d["areas"])


def test_a_person_answers_a_line_with_their_name_and_the_answer_is_logged(client):  # noqa: F811
    c = client
    r = c.put(
        "/checklists/cbam-scope", json={"state": "done", "note": "steel parts, checked", "set_by": "anna"}
    )
    assert r.status_code == 200 and r.json()["progress"]["set_by"] == "anna"
    r = c.put("/checklists/cbam-scope", json={"state": "todo", "set_by": "boris"})  # changing it is allowed
    assert r.json()["progress"]["state"] == "todo" and r.json()["progress"]["set_by"] == "boris"
    assert c.session.query(ChecklistProgress).count() == 1
    log = c.session.query(AuditLog).filter(AuditLog.action == "checklist.set").all()
    assert [(x.actor_id, x.payload["from"], x.payload["to"]) for x in log] == [
        ("anna", None, "done"),
        ("boris", "done", "todo"),
    ]
    c.put("/checklists/sef-b2b", json={"state": "done", "set_by": "anna"})
    area = next(a for a in c.get("/checklists").json()["areas"] if a["key"] == "rs_sef")
    assert area["answered"] == 1


def test_answers_are_checked(client):  # noqa: F811
    c = client
    ok = {"state": "done", "set_by": "anna"}
    assert c.put("/checklists/nope", json=ok).status_code == 404
    assert c.put("/checklists/cbam-scope", json={**ok, "state": "maybe"}).status_code == 422
    assert c.put("/checklists/cbam-scope", json={**ok, "set_by": " "}).status_code == 409
    assert c.put("/checklists/cbam-scope", json={**ok, "state": "not_applicable"}).status_code == 422
    assert (
        c.put("/checklists/cbam-scope", json={**ok, "state": "not_applicable", "note": "we do not import"})
    ).status_code == 200
    assert STATES == ("todo", "done", "not_applicable")


def test_roles_for_the_checklists():
    assert rules.allowed(["buyer"], "PUT", "/checklists/cbam-scope")
    assert rules.allowed(["legal"], "PUT", "/checklists/cbam-scope")
    assert not rules.allowed(["approver"], "PUT", "/checklists/cbam-scope")
    assert rules.allowed(["approver"], "GET", "/checklists")
