"""Supplier profiles, sorting and filters, due-diligence checks, and the access vault."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import config
from app.config import Settings, get_settings, set_overrides
from app.main import app
from app.models import AuditLog, Supplier, VaultEntry, VaultLog, VaultRequest
from app.seed import fill_profiles
from tests.test_pipeline_e2e import client, new_request  # noqa: F401

WHO = {"changed_by": "Kartel"}


@pytest.fixture
def c(client, tmp_path):  # noqa: F811
    cfg = Settings(_env_file=None, data_dir=str(tmp_path))
    app.dependency_overrides[get_settings] = lambda: cfg.model_copy(update=dict(config._overrides))
    set_overrides({})
    fill_profiles(client.session)
    yield client
    set_overrides({})


def overview(c, **params):
    r = c.get("/suppliers/overview", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_name(rows, name):
    return next(r for r in rows if r["name"] == name)


# ---- profiles ---------------------------------------------------------------------------------


def test_demo_suppliers_have_profiles_and_the_fill_is_repeatable(c):
    rows = overview(c)
    stocked = [r for r in rows if r["catalog_lines"]]
    assert stocked and all(r["brands"] and r["brand_tiers"] and r["partner_status"] for r in stocked)
    assert set(stocked[0]["brand_tiers"]) == set(stocked[0]["brands"])
    assert fill_profiles(c.session) == 0  # nothing left to fill


def test_profile_edit_validates_and_needs_a_person(c):
    sid = overview(c)[0]["id"]
    ok = c.patch(
        f"/suppliers/{sid}",
        json={"changes": {"brands": ["Dell", "dell", " HP "], "brand_tiers": {"Dell": "vendor"}}, **WHO},
    )
    assert ok.status_code == 200
    row = c.get(f"/suppliers/{sid}").json()
    assert row["brands"] == ["Dell", "HP"] and row["brand_tiers"] == {"Dell": "vendor"}
    bad = c.patch(f"/suppliers/{sid}", json={"changes": {"brand_tiers": {"Dell": "boss"}}, **WHO})
    assert bad.status_code == 422
    assert c.patch(f"/suppliers/{sid}", json={"changes": {"payment_type": "cash"}, **WHO}).status_code == 422
    assert c.patch(f"/suppliers/{sid}", json={"changes": {"partner_status": "x"}, **WHO}).status_code == 422
    assert (
        c.patch(f"/suppliers/{sid}", json={"changes": {"brands": ["A"]}, "changed_by": " "}).status_code
        == 409
    )


def test_discounts_are_added_removed_and_audited(c):
    sid = overview(c)[0]["id"]
    r = c.post(f"/suppliers/{sid}/discounts", json={"brand": "Dell", "description": "7% from 50 pcs", **WHO})
    assert r.status_code == 200
    assert any(d["id"] == r.json()["id"] for d in c.get(f"/suppliers/{sid}").json()["discounts"])
    assert (
        c.post(f"/suppliers/{sid}/discounts", json={"brand": "", "description": "x", **WHO}).status_code
        == 422
    )
    assert c.delete(f"/suppliers/discounts/{r.json()['id']}", params=WHO).status_code == 200
    actions = {a.action for a in c.session.scalars(select(AuditLog))}
    assert {"supplier.discount_added", "supplier.discount_removed"} <= actions


# ---- sorting and filters ----------------------------------------------------------------------


def test_sorting_by_each_key_and_empty_values_go_last(c):
    rows = overview(c, sort="deals_count", dir="desc")
    deals = [r["deals_count"] for r in rows]
    assert deals == sorted(deals, reverse=True)
    assert [r["name"] for r in overview(c, sort="name", dir="asc")] == sorted(
        (r["name"] for r in rows), key=str.casefold
    )
    sup = c.session.get(Supplier, rows[0]["id"])
    sup.stock_delivery_days = None
    c.session.commit()
    for direction in ("asc", "desc"):
        got = overview(c, sort="stock_delivery_days", dir=direction)
        assert got[-1]["id"] == sup.id and got[-1]["stock_delivery_days"] is None
    asc = [
        r["stock_delivery_days"]
        for r in overview(c, sort="stock_delivery_days")
        if r["stock_delivery_days"] is not None
    ]
    assert asc == sorted(asc)
    for key in (
        "country",
        "age_years",
        "payment_terms_days",
        "warranty_months",
        "partner_status",
        "check",
        "brands",
    ):
        assert len(overview(c, sort=key)) == len(rows)
    assert c.get("/suppliers/overview", params={"sort": "salary"}).status_code == 422
    assert c.get("/suppliers/overview", params={"dir": "up"}).status_code == 422


def test_filters_combine_and_facets_narrow_level_by_level(c):
    everything = overview(c)
    country = next(r["country"] for r in everything if r["country"] != "RS")
    only = overview(c, country=country)
    assert only and all(r["country"] == country for r in only)
    brand = only[0]["brands"][0]
    both = overview(c, country=country, brand=brand.lower())
    assert both and all(brand in r["brands"] for r in both) and len(both) <= len(only)
    assert overview(c, q="no-such-supplier-xyz") == []

    all_facets = c.get("/suppliers/facets").json()
    narrowed = c.get("/suppliers/facets", params={"country": country}).json()
    assert {x["value"] for x in all_facets["countries"]} == {r["country"] for r in everything}
    assert {x["value"] for x in narrowed["categories"]} == {cat for r in only for cat in r["categories"]}
    cat = narrowed["categories"][0]["value"]
    deeper = c.get("/suppliers/facets", params={"country": country, "category": cat}).json()
    expected = {b for r in only if cat in r["categories"] for b in r["brands"]}
    assert {x["value"] for x in deeper["brands"]} == expected
    assert sum(x["count"] for x in all_facets["countries"]) == len(everything)


# ---- checks -----------------------------------------------------------------------------------


def test_checks_keep_history_and_the_newest_one_counts(c):
    sid = overview(c)[0]["id"]
    assert (
        c.post(f"/suppliers/{sid}/checks", json={"result": "working", "checked_by": " "}).status_code == 409
    )
    assert (
        c.post(f"/suppliers/{sid}/checks", json={"result": "great", "checked_by": "Kartel"}).status_code
        == 422
    )
    assert (
        c.post("/suppliers/9999/checks", json={"result": "working", "checked_by": "Kartel"}).status_code
        == 404
    )
    c.post(f"/suppliers/{sid}/checks", json={"result": "under_review", "checked_by": "Ana", "note": "called"})
    c.post(
        f"/suppliers/{sid}/checks",
        json={"result": "working", "checked_by": "Kartel", "contact_details": "+381"},
    )
    detail = c.get(f"/suppliers/{sid}").json()
    assert detail["check_result"] == "working" and [x["result"] for x in detail["checks"]] == [
        "working",
        "under_review",
    ]
    assert [r["supplier_id"] for r in c.get("/suppliers/checks", params={"result": "working"}).json()] == [
        sid
    ]
    unchecked = c.get("/suppliers/checks", params={"result": "unchecked"}).json()
    assert sid not in {r["supplier_id"] for r in unchecked} and unchecked
    assert [r["id"] for r in overview(c, check="working")] == [sid]


def test_a_supplier_that_does_not_work_is_left_out_of_the_shortlist(c):
    rid = new_request(c)
    c.post(f"/requests/{rid}/discover")
    listed = c.get(f"/requests/{rid}/shortlist").json()
    victim, review = listed[0]["supplier"], listed[1]["supplier"]
    ids = {s["name"]: s["id"] for s in overview(c)}
    c.post(f"/suppliers/{ids[victim]}/checks", json={"result": "not_working", "checked_by": "Kartel"})
    c.post(f"/suppliers/{ids[review]}/checks", json={"result": "under_review", "checked_by": "Kartel"})
    c.post(f"/requests/{rid}/discover")
    after = c.get(f"/requests/{rid}/shortlist").json()
    assert victim not in [s["supplier"] for s in after]
    assert "check under review" in next(s for s in after if s["supplier"] == review)["reason"]
    c.post(f"/suppliers/{ids[victim]}/checks", json={"result": "working", "checked_by": "Kartel"})
    c.post(f"/requests/{rid}/discover")
    assert victim in [s["supplier"] for s in c.get(f"/requests/{rid}/shortlist").json()]


# ---- vault ------------------------------------------------------------------------------------

SECRET = {"login": "buyer-7@example.test", "password": "S3cret-Pass!word"}


def new_entry(c, **over):
    body = {
        "category": "supplier portal",
        "name": "Acme portal",
        "site_url": "https://acme.example",
        **SECRET,
        **WHO,
        **over,
    }
    r = c.post("/vault", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_secrets_are_encrypted_and_never_listed_or_logged(c):
    eid = new_entry(c)
    listing = c.get("/vault")
    assert SECRET["password"] not in listing.text and SECRET["login"] not in listing.text
    row = c.session.get(VaultEntry, eid)
    assert SECRET["password"] not in row.password_encrypted and SECRET["login"] not in row.login_encrypted
    blob = str([(x.event, x.detail) for x in c.session.scalars(select(VaultLog))])
    blob += str([a.payload for a in c.session.scalars(select(AuditLog))])
    assert SECRET["password"] not in blob and SECRET["login"] not in blob


def test_seeing_a_secret_needs_a_second_person_and_works_once(c):
    eid = new_entry(c)
    assert c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": " "}).status_code == 422
    req = c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": "re-order"}).json()
    assert req["status"] == "pending"
    assert (
        c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": "again"}).status_code == 409
    )
    reveal = f"/vault/requests/{req['id']}/reveal"
    assert c.post(reveal, json={"person": "Ana"}).status_code == 409  # not approved yet
    own = c.post(f"/vault/requests/{req['id']}/decide", json={"decided_by": "ana", "approve": True})
    assert own.status_code == 409  # cannot approve your own request
    ok = c.post(f"/vault/requests/{req['id']}/decide", json={"decided_by": "Boris", "approve": True})
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["approved_until"]
    assert c.post(reveal, json={"person": "Boris"}).status_code == 409  # only the requester can open it
    shown = c.post(reveal, json={"person": "Ana"})
    assert shown.status_code == 200 and shown.json()["login"] == SECRET["login"]
    assert shown.json()["password"] == SECRET["password"]
    assert c.post(reveal, json={"person": "Ana"}).status_code == 409  # used
    events = [e["event"] for e in c.get("/vault/log").json()]
    assert {"created", "requested", "approved", "revealed"} <= set(events)


def test_rejected_and_expired_approvals_do_not_open(c):
    eid = new_entry(c)
    req = c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": "x"}).json()
    c.post(
        f"/vault/requests/{req['id']}/decide", json={"decided_by": "Boris", "approve": False, "comment": "no"}
    )
    assert c.post(f"/vault/requests/{req['id']}/reveal", json={"person": "Ana"}).status_code == 409
    again = c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": "y"}).json()
    c.post(f"/vault/requests/{again['id']}/decide", json={"decided_by": "Boris", "approve": True})
    row = c.session.get(VaultRequest, again["id"])
    row.decided_at = datetime.now(UTC) - timedelta(minutes=16)
    c.session.commit()
    r = c.post(f"/vault/requests/{again['id']}/reveal", json={"person": "Ana"})
    assert r.status_code == 409 and "expired" in r.json()["detail"]
    assert [x["status"] for x in c.get("/vault/requests").json() if x["id"] == again["id"]] == ["expired"]


def test_editing_and_deleting_entries_need_a_person_and_are_logged(c):
    eid = new_entry(c)
    assert c.patch(f"/vault/{eid}", json={"name": "New", "changed_by": " "}).status_code == 409
    assert c.patch(f"/vault/{eid}", json={"category": "nonsense", **WHO}).status_code == 422
    assert (
        c.post(
            "/vault", json={"category": "other", "name": "x", "login": "", "password": "p", **WHO}
        ).status_code
        == 422
    )
    r = c.patch(f"/vault/{eid}", json={"password": "N3w-Pass", "comments": "rotated", **WHO})
    assert r.status_code == 200 and r.json()["comments"] == "rotated" and "password" not in r.json()
    req = c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": "x"}).json()
    c.post(f"/vault/requests/{req['id']}/decide", json={"decided_by": "Boris", "approve": True})
    assert (
        c.post(f"/vault/requests/{req['id']}/reveal", json={"person": "Ana"}).json()["password"] == "N3w-Pass"
    )
    assert c.delete(f"/vault/{eid}", params=WHO).status_code == 200
    assert c.get("/vault").json()["entries"] == []
    assert {"updated", "deleted"} <= {e["event"] for e in c.get("/vault/log").json()}


def test_a_replaced_key_is_reported_not_crashed(c, tmp_path):
    eid = new_entry(c)
    req = c.post(f"/vault/{eid}/requests", json={"requested_by": "Ana", "reason": "x"}).json()
    c.post(f"/vault/requests/{req['id']}/decide", json={"decided_by": "Boris", "approve": True})
    (tmp_path / "secret.key").unlink()  # a new key is generated on next use
    r = c.post(f"/vault/requests/{req['id']}/reveal", json={"person": "Ana"})
    assert r.status_code == 409 and "cannot be decrypted" in r.json()["detail"]
