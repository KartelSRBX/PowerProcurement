"""Supplier re-checks: a person records a sanctions screening (date, list, result) and the beneficiary;
the app shows what is overdue, never done or coming due. No list is downloaded and nothing is blocked."""

from datetime import date, timedelta

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from app.models import AuditLog
from app.suppliers.compliance import add_months
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401
from tests.test_supplier_duplicates import _add

LIST = "EU consolidated list"


def _shot(c, sid, days_ago=0, **over):
    body = {
        "checked_by": "kartel",
        "checked_on": (date.today() - timedelta(days=days_ago)).isoformat(),
        "list_name": LIST,
        "result": "clear",
        **over,
    }
    return c.post(f"/suppliers/{sid}/screenings", json=body)


def _item(c, sid):
    items = c.get("/suppliers/rechecks").json()["items"]
    return next((i for i in items if i["supplier_id"] == sid), None)


def test_months_are_added_with_the_day_clamped():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 12) == date(2027, 11, 15)
    assert add_months(date(2026, 12, 31), 2) == date(2027, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


def test_a_supplier_never_screened_is_listed_and_a_recent_screening_takes_it_off(client):  # noqa: F811
    c = client
    sid = _add(c, "Fresh Supplier")
    first = _item(c, sid)
    assert first["screening"]["status"] == "never" and "never screened" in first["reasons"]
    assert _shot(c, sid).status_code == 200
    item = _item(c, sid)
    assert item["screening"]["status"] == "ok" and "never screened" not in item["reasons"]
    assert item["reasons"] == [
        "beneficiary not recorded"
    ]  # the screening is current; the owner is still missing


def test_overdue_and_due_soon_follow_the_default_period_and_the_warning_window(client):  # noqa: F811
    c = client
    old, soon, fine = (_add(c, n) for n in ("Old Check", "Soon Check", "Fine Check"))
    _shot(c, old, days_ago=400)  # 12 months default: due about 35 days ago
    _shot(c, soon, days_ago=345)  # due in about 20 days: inside the 30 day window
    _shot(c, fine, days_ago=10)
    assert _item(c, old)["screening"]["status"] == "overdue"
    assert any("overdue by" in r for r in _item(c, old)["reasons"])
    assert _item(c, soon)["screening"]["status"] == "due_soon"
    assert all("screening" not in r for r in _item(c, fine)["reasons"])
    ranked = [i["supplier_id"] for i in c.get("/suppliers/rechecks").json()["items"]]
    assert ranked.index(old) < ranked.index(soon)  # overdue comes before coming due


def test_the_period_can_be_changed_for_one_supplier_and_in_settings(client):  # noqa: F811
    c = client
    sid = _add(c, "Short Period")
    _shot(c, sid, days_ago=200)
    assert _item(c, sid)["screening"]["status"] == "ok"
    body = {"changed_by": "kartel", "period_months": 6, "next_check_on": None}
    assert c.put(f"/suppliers/{sid}/recheck-schedule", json={**body, "changed_by": " "}).status_code == 409
    assert c.put(f"/suppliers/{sid}/recheck-schedule", json={**body, "period_months": 0}).status_code == 422
    assert c.put(f"/suppliers/{sid}/recheck-schedule", json=body).status_code == 200
    assert _item(c, sid)["screening"]["status"] == "overdue"  # 6 months after 200 days ago
    assert c.get(f"/suppliers/{sid}/compliance").json()["screening"]["own_period"] is True
    # the default for everyone comes from Settings
    other = _add(c, "Default Period")
    _shot(c, other, days_ago=200)
    try:
        app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update={"recheck_months": 3})
        assert _item(c, other)["screening"]["status"] == "overdue"
    finally:
        app.dependency_overrides[get_settings] = lambda: SETTINGS


def test_a_date_set_by_a_person_wins_and_is_used_up_by_a_later_screening(client):  # noqa: F811
    c = client
    sid = _add(c, "Dated Check")
    _shot(c, sid, days_ago=5)
    soon = (date.today() + timedelta(days=10)).isoformat()
    c.put(f"/suppliers/{sid}/recheck-schedule", json={"changed_by": "kartel", "next_check_on": soon})
    v = c.get(f"/suppliers/{sid}/compliance").json()
    assert v["screening"]["status"] == "due_soon" and v["screening"]["due_on"] == soon
    assert v["screening"]["basis"] == "a date set by a person"
    _shot(c, sid)  # today is before the chosen date: the date stays
    assert c.get(f"/suppliers/{sid}/compliance").json()["next_check_on"] == soon
    c.put(
        f"/suppliers/{sid}/recheck-schedule",
        json={"changed_by": "kartel", "next_check_on": date.today().isoformat()},
    )
    _shot(c, sid)  # on or after the chosen date: it is used up and the period counts again
    v = c.get(f"/suppliers/{sid}/compliance").json()
    assert v["next_check_on"] is None and v["screening"]["status"] == "ok"
    assert [
        a.payload["cleared_date"] is not None
        for a in c.session.query(AuditLog).filter_by(action="supplier.screened")
    ][-1]


def test_a_match_needs_a_note_and_stays_on_the_list_until_a_later_clear_result(client):  # noqa: F811
    c = client
    sid = _add(c, "Flagged Supplier")
    assert _shot(c, sid, result="match").status_code == 422
    assert _shot(c, sid, result="maybe").status_code == 422
    assert _shot(c, sid, list_name=" ").status_code == 422
    assert _shot(c, sid, days_ago=-1).status_code == 422
    assert _shot(c, sid, checked_by=" ").status_code == 409
    assert (
        c.post(
            "/suppliers/99999/screenings",
            json={"checked_by": "k", "checked_on": "2026-01-01", "list_name": "x", "result": "clear"},
        ).status_code
        == 404
    )
    assert (
        _shot(
            c, sid, days_ago=3, result="match", note="same name as a listed company, different country"
        ).status_code
        == 200
    )
    item = _item(c, sid)
    assert item["screening"]["attention"] and item["reasons"][0].startswith(
        "last screening: a possible match"
    )
    assert c.get("/suppliers/rechecks").json()["items"][0]["supplier_id"] == sid  # attention comes first
    assert _shot(c, sid, result="clear", note="checked the registry: not the same company").status_code == 200
    assert not _item(c, sid)["screening"]["attention"]
    # nothing else changed: the supplier is not marked sanctioned by the app
    assert c.get(f"/suppliers/{sid}").json()["sanctioned"] is False


def test_the_beneficiary_is_recorded_with_its_source_and_goes_stale(client):  # noqa: F811
    c = client
    sid = _add(c, "Owned Supplier")
    body = {
        "confirmed_by": "kartel",
        "owners": ["Jana Novak", " jana  novak ", "Petr Svoboda"],
        "source": "business_register",
        "confirmed_on": date.today().isoformat(),
    }
    assert c.put(f"/suppliers/{sid}/beneficiary", json={**body, "confirmed_by": " "}).status_code == 409
    assert c.put(f"/suppliers/{sid}/beneficiary", json={**body, "source": "hearsay"}).status_code == 422
    assert c.put(f"/suppliers/{sid}/beneficiary", json={**body, "owners": []}).status_code == 422
    assert c.put(f"/suppliers/{sid}/beneficiary", json={**body, "source": "other"}).status_code == 422
    future = (date.today() + timedelta(days=2)).isoformat()
    assert c.put(f"/suppliers/{sid}/beneficiary", json={**body, "confirmed_on": future}).status_code == 422
    assert c.put(f"/suppliers/{sid}/beneficiary", json=body).status_code == 200
    ben = c.get(f"/suppliers/{sid}/compliance").json()["beneficiary"]
    assert (
        ben["owners"] == ["Jana Novak", "Petr Svoboda"]
        and ben["status"] == "ok"
        and ben["confirmed_by"] == "kartel"
    )
    old = {**body, "confirmed_on": (date.today() - timedelta(days=500)).isoformat()}
    c.put(f"/suppliers/{sid}/beneficiary", json=old)
    assert _item(c, sid)["beneficiary"]["status"] == "overdue"
    nobody = {**body, "owners": [], "note": "state-owned, no natural person owner"}
    assert c.put(f"/suppliers/{sid}/beneficiary", json=nobody).status_code == 200
    actions = [
        a.action for a in c.session.query(AuditLog).filter(AuditLog.action.like("supplier.beneficiary%"))
    ]
    assert len(actions) == 3


def test_suppliers_on_hold_are_left_out_and_a_screening_can_be_removed(client):  # noqa: F811
    c = client
    sid = _add(c, "Held Supplier")
    assert _item(c, sid) is not None
    c.patch(f"/suppliers/{sid}", json={"changes": {"partner_status": "on_hold"}, "changed_by": "kartel"})
    assert _item(c, sid) is None
    c.patch(f"/suppliers/{sid}", json={"changes": {"partner_status": "approved"}, "changed_by": "kartel"})
    _shot(c, sid)
    rid = c.get(f"/suppliers/{sid}/compliance").json()["last"]["id"]
    assert c.delete(f"/screenings/{rid}", params={"removed_by": " "}).status_code == 409
    v = c.delete(f"/screenings/{rid}", params={"removed_by": "marko"})
    assert v.status_code == 200 and v.json()["last"] is None and v.json()["screening"]["status"] == "never"
    assert c.delete("/screenings/99999", params={"removed_by": "marko"}).status_code == 404


def test_the_settings_for_rechecks_are_saved_and_checked(client):  # noqa: F811
    c = client
    try:
        app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
        body = {"changed_by": "kartel", "months": 6, "warn_days": 14}
        assert c.put("/settings/rechecks", json={**body, "changed_by": " "}).status_code == 422
        assert c.put("/settings/rechecks", json={**body, "months": 0}).status_code == 422
        r = c.put("/settings/rechecks", json=body)
        assert r.status_code == 200 and r.json()["rechecks"] == {"months": 6, "warn_days": 14}
    finally:
        set_overrides({})
