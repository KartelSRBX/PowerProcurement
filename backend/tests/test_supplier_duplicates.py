"""The duplicate supplier finder: same tax number, same bank account, same or similar name. It lists pairs for
a person to review and never merges or blocks anything."""

import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.main import app
from app.models import AuditLog, Supplier
from app.suppliers import duplicates
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401
from tests.test_supplier_bank import IBAN, _body, _decide

WHO = {"changed_by": "kartel"}


@pytest.fixture
def keyed(client):  # noqa: F811
    key = Fernet.generate_key().decode()
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update={"app_secret_key": key})
    return client


def _add(c, name, country="DE", tax_id=None):
    s = Supplier(
        name=name, country=country, email=f"x@{abs(hash(name))}.example", categories=[], languages=["en"],
        age_years=5, vat_verified=True, deals_count=1, framework_contract=False,
        payment_terms_days=30, warranty_months=12, tax_id=tax_id,
    )  # fmt: skip
    c.session.add(s)
    c.session.commit()
    return s.id


def _pairs(c, **params):
    r = c.get("/suppliers/duplicates", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _mine(c, ids, **params):
    """Pairs among the given suppliers (the seeded demo suppliers must not interfere)."""
    return [p for p in _pairs(c, **params)["pairs"] if p["a"]["id"] in ids and p["b"]["id"] in ids]


def test_name_and_tax_keys_ignore_legal_forms_prefixes_and_punctuation():
    assert duplicates.name_key("Acme Elektronik GmbH") == duplicates.name_key("ACME  Elektronik, d.o.o.")
    assert duplicates.name_key("Müller & Söhne Ltd.") == "müller söhne"
    assert duplicates.tax_key("RS 100.123-456") == "100123456" == duplicates.tax_key("100123456")
    assert (
        duplicates.tax_key("12") is None
        and duplicates.tax_key(None) is None
        and duplicates.tax_key("  ") is None
    )


def test_the_same_tax_number_is_found_whatever_the_prefix(client):  # noqa: F811
    c = client
    a = _add(c, "Nord Parts", tax_id="RS100123456")
    b = _add(c, "Completely Other Name", tax_id="100 123 456")
    _add(c, "Third Company", tax_id="999888777")
    pairs = _mine(c, {a, b})
    assert len(pairs) == 1 and pairs[0]["strength"] == 3
    assert [r["kind"] for r in pairs[0]["reasons"]] == ["tax_id"]
    assert (pairs[0]["a"]["id"], pairs[0]["b"]["id"]) == (a, b)


def test_a_tax_number_shared_across_countries_says_so(client):  # noqa: F811
    c = client
    a = _add(c, "Alpha Trade", country="DE", tax_id="123456789")
    b = _add(c, "Beta Supply", country="RS", tax_id="123456789")
    reason = _mine(c, {a, b})[0]["reasons"][0]
    assert "different countries" in reason["detail"]


def test_same_name_apart_from_legal_form_and_a_similar_name(client):  # noqa: F811
    c = client
    a = _add(c, "Dunav Components d.o.o.", country="RS")
    b = _add(c, "DUNAV COMPONENTS GmbH", country="DE")
    d = _add(c, "Danube Components")
    e = _add(c, "Danube Component")
    assert [r["kind"] for r in _mine(c, {a, b})[0]["reasons"]] == ["name_same"]
    similar = _mine(c, {d, e})
    assert [r["kind"] for r in similar[0]["reasons"]] == ["name_similar"] and similar[0]["strength"] == 1
    assert _mine(c, {a, d}) == []  # nothing in common


def test_the_same_bank_account_is_found_without_opening_it(keyed):
    c = keyed
    a = _add(c, "Nord Parts")
    b = _add(c, "Sued Bauteile")
    for sid, holder in ((a, "Nord Parts"), (b, "Sued Bauteile")):
        cid = c.post(f"/suppliers/{sid}/bank/proposals", json=_body(holder=holder)).json()
        if sid == a:
            _decide(c, cid["pending"]["id"])  # the first is in force, the second is still proposed
    pairs = _mine(c, {a, b})
    assert [r["kind"] for r in pairs[0]["reasons"]] == ["bank_account"] and pairs[0]["strength"] == 3
    assert IBAN not in str(pairs)  # the account itself is never in the list


def test_a_review_hides_a_pair_until_a_new_signal_appears(client):  # noqa: F811
    c = client
    a = _add(c, "Acme Trading GmbH", tax_id="55566677")
    b = _add(c, "Acme Trading Ltd")
    bad = {"supplier_a_id": b, "supplier_b_id": a, "verdict": "different", "reviewed_by": "kartel"}
    assert c.post("/suppliers/duplicates/review", json={**bad, "note": " "}).status_code == 422
    assert (
        c.post("/suppliers/duplicates/review", json={**bad, "note": "ok", "reviewed_by": " "}).status_code
        == 409
    )
    assert (
        c.post("/suppliers/duplicates/review", json={**bad, "note": "ok", "verdict": "maybe"}).status_code
        == 422
    )
    r = c.post(
        "/suppliers/duplicates/review", json={**bad, "note": "two group companies, separate tax numbers"}
    )
    assert r.status_code == 200 and r.json()["review"]["verdict"] == "different"
    assert (r.json()["a"]["id"], r.json()["b"]["id"]) == (a, b)  # the pair is stored smaller id first
    assert _mine(c, {a, b}) == [] and _pairs(c)["hidden"] == 1
    assert len(_mine(c, {a, b}, include_reviewed=True)) == 1
    # later both get the same tax number: the dismissed pair comes back
    c.patch(f"/suppliers/{b}", json={"changes": {"tax_id": "RS55566677"}, **WHO})
    back = _mine(c, {a, b})
    assert (
        len(back) == 1
        and back[0]["reappeared"]
        and {x["kind"] for x in back[0]["reasons"]} == {"name_same", "tax_id"}
    )


def test_a_pair_confirmed_as_the_same_company_stays_listed_and_a_review_can_be_removed(client):  # noqa: F811
    c = client
    a = _add(c, "Zeta Elektronik GmbH")
    b = _add(c, "Zeta Elektronik d.o.o.")
    r = c.post(
        "/suppliers/duplicates/review",
        json={
            "supplier_a_id": a,
            "supplier_b_id": b,
            "verdict": "same",
            "note": "same owner, merge later",
            "reviewed_by": "marko",
        },
    )
    assert r.status_code == 200
    shown = _mine(c, {a, b})
    assert shown[0]["review"]["verdict"] == "same" and shown[0]["review"]["reviewed_by"] == "marko"
    rid = shown[0]["review"]["id"]
    assert c.delete(f"/suppliers/duplicates/review/{rid}", params={"removed_by": " "}).status_code == 409
    assert c.delete(f"/suppliers/duplicates/review/{rid}", params={"removed_by": "marko"}).status_code == 200
    assert _mine(c, {a, b})[0]["review"] is None
    actions = [
        x.action for x in c.session.query(AuditLog).filter(AuditLog.action.like("supplier.duplicate%"))
    ]
    assert actions == ["supplier.duplicate_reviewed", "supplier.duplicate_review_removed"]


def test_reviewing_needs_a_shared_signal_and_real_suppliers(client):  # noqa: F811
    c = client
    a, b = _add(c, "Qqq One"), _add(c, "Www Two")
    body = {
        "supplier_a_id": a,
        "supplier_b_id": b,
        "verdict": "different",
        "note": "just checking",
        "reviewed_by": "kartel",
    }
    assert c.post("/suppliers/duplicates/review", json=body).status_code == 422
    assert c.post("/suppliers/duplicates/review", json={**body, "supplier_b_id": a}).status_code == 422
    assert c.post("/suppliers/duplicates/review", json={**body, "supplier_b_id": 99999}).status_code == 404


def test_a_supplier_shows_its_possible_duplicates_and_creating_one_warns(client):  # noqa: F811
    c = client
    a = _add(c, "Omega Distribution", tax_id="777000111")
    created = c.post(
        "/suppliers",
        json={
            "name": "Omega Distribution Ltd",
            "country": "GB",
            "email": "o@omega.example",
            "tax_id": "GB777000111",
            **WHO,
        },
    )
    assert created.status_code == 200
    new_id = created.json()["id"]
    kinds = {r["kind"] for p in created.json()["possible_duplicates"] for r in p["reasons"]}
    assert kinds == {"name_same", "tax_id"}
    detail = c.get(f"/suppliers/{a}").json()
    assert [p["b"]["id"] for p in detail["possible_duplicates"]] == [new_id]
    assert detail["tax_id"] == "777000111"
    assert c.patch(f"/suppliers/{a}", json={"changes": {"tax_id": "x" * 41}, **WHO}).status_code == 422
