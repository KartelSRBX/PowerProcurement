"""Request urgency: a flag and a reply-by date set by a person, and the board of requests still open."""

from datetime import date, timedelta

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from app.models import AuditLog, CustomerRequest
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import SETTINGS, client, new_request  # noqa: F401


def _in(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _set(c, rid, **over):
    body = {
        "changed_by": "kartel",
        "urgent": True,
        "respond_by": _in(3),
        "note": "customer line is down",
        **over,
    }
    return c.put(f"/requests/{rid}/urgency", json=body)


def _board(c):
    r = c.get("/requests/urgent")
    assert r.status_code == 200, r.text
    return r.json()


def _row(c, rid):
    return next((i for i in _board(c)["items"] if i["request_id"] == rid), None)


def test_nothing_is_urgent_until_a_person_says_so(client):  # noqa: F811
    c = client
    rid = new_request(c)
    assert _board(c)["items"] == []
    d = c.get(f"/requests/{rid}/urgency").json()
    assert d["urgent"] is False and d["respond_by"] is None and d["state"] == "no_date"
    assert c.get("/requests/99999/urgency").status_code == 404
    listed = next(r for r in c.get("/requests").json() if r["id"] == rid)
    assert listed["urgent"] is False and listed["respond_by"] is None


def test_setting_needs_a_person_and_a_date_not_in_the_past_and_is_logged(client):  # noqa: F811
    c = client
    rid = new_request(c)
    assert _set(c, rid, changed_by=" ").status_code == 409
    assert _set(c, rid, respond_by=_in(-1)).status_code == 422
    assert _set(c, 99999).status_code == 404
    r = _set(c, rid)
    assert r.status_code == 200 and r.json()["urgent"] and r.json()["respond_by"] == _in(3)
    assert r.json()["state"] == "later" and r.json()["days_left"] == 3 and r.json()["set_by"] == "kartel"
    log = c.session.query(AuditLog).filter_by(action="request.urgency").one()
    assert log.payload["after"]["respond_by"] == _in(3) and log.payload["before"]["urgent"] is False
    listed = next(x for x in c.get("/requests").json() if x["id"] == rid)
    assert listed["urgent"] and listed["respond_by"] == _in(3)
    # an old date can stay when only the note or the flag changes
    req = c.session.get(CustomerRequest, rid)
    req.respond_by = date.today() - timedelta(days=2)
    c.session.commit()
    assert _set(c, rid, respond_by=_in(-2), note="still waiting").status_code == 200


def test_the_board_orders_overdue_then_today_then_urgent_without_date_then_the_rest(client):  # noqa: F811
    c = client
    ids = [new_request(c) for _ in range(5)]
    late, today, nodate, soon, later = ids
    for rid in ids:
        _set(c, rid, urgent=False, respond_by=_in(5))
    _set(c, nodate, urgent=True, respond_by=None)
    _set(c, soon, urgent=False, respond_by=_in(2))
    _set(c, today, urgent=False, respond_by=_in(0))
    _set(c, later, urgent=False, respond_by=_in(9))
    for rid, d in ((late, -4),):
        c.session.get(CustomerRequest, rid).respond_by = date.today() + timedelta(days=d)
    c.session.commit()
    b = _board(c)
    assert [i["request_id"] for i in b["items"]] == [late, today, nodate, soon, later]
    assert [i["state"] for i in b["items"]] == ["overdue", "today", "no_date", "soon", "later"]
    assert b["items"][0]["days_left"] == -4
    assert b["counts"] == {"overdue": 1, "today": 1, "urgent": 1, "total": 5}


def test_a_request_leaves_the_board_when_its_quote_is_sent_and_a_not_request_never_enters(client):  # noqa: F811
    c = client
    rid, sids, _ = _setup(c)
    _offer(c, rid, sids[0], [10, 20])
    assert _set(c, rid).status_code == 200
    assert _row(c, rid)["stage"] == "offers_in" and _row(c, rid)["next"]
    ranked = c.post(f"/requests/{rid}/score").json()
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": ranked[0]["offer_id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    assert _row(c, rid)["stage"] == "quote_draft"  # a draft is not an answer to the customer yet
    sent = c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "marko"}).json()
    assert sent["status"] == "sent" and _row(c, rid) is None  # answered: off the board, flag kept
    assert c.get(f"/requests/{rid}/urgency").json()["urgent"] is True
    other = new_request(c)
    c.session.get(CustomerRequest, other).status = "not_request"
    c.session.commit()
    assert _set(c, other).status_code == 409


def test_the_warning_window_is_a_setting(client):  # noqa: F811
    c = client
    rid = new_request(c)
    _set(c, rid, respond_by=_in(4))
    assert _row(c, rid)["state"] == "later"  # 2 days by default
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    try:
        body = {"changed_by": "kartel", "warn_days": 5}
        assert c.put("/settings/urgency", json={**body, "changed_by": " "}).status_code == 422
        assert c.put("/settings/urgency", json={**body, "warn_days": 31}).status_code == 422
        r = c.put("/settings/urgency", json=body)
        assert r.status_code == 200 and r.json()["urgency"] == {"warn_days": 5}
        assert _row(c, rid)["state"] == "soon"
    finally:
        set_overrides({})
