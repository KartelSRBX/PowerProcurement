"""Supplier bank details: an account is set or changed only as a proposal with a record of the call,
and takes effect when a different person approves. The code checks the IBAN and warns; people decide."""

from datetime import date, timedelta

import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.main import app
from app.models import AuditLog, Supplier, SupplierBankAccount, SupplierBankChange
from app.suppliers import bank
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401

IBAN = "DE89370400440532013000"
IBAN2 = "GB82WEST12345698765432"


@pytest.fixture
def keyed(client):  # noqa: F811
    key = Fernet.generate_key().decode()
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update={"app_secret_key": key})
    return client


def _supplier(c, name="Acme Elektronik GmbH", country="DE"):
    s = Supplier(
        name=name, country=country, email=f"x@{name[:4].lower()}.example", categories=[], languages=["en"],
        age_years=5, vat_verified=True, deals_count=1, framework_contract=False,
        payment_terms_days=30, warranty_months=12,
    )  # fmt: skip
    c.session.add(s)
    c.session.commit()
    return s.id


def _body(**over):
    return {
        "proposed_by": "kartel",
        "account": IBAN,
        "holder": "Acme Elektronik GmbH",
        "reason": "new supplier",
        "callback_by": "kartel",
        "callback_person": "Frau Weber, accounts",
        "callback_source": "contract",
        "callback_on": date.today().isoformat(),
        **over,
    }


def _propose(c, sid, **over):
    return c.post(f"/suppliers/{sid}/bank/proposals", json=_body(**over))


def _decide(c, cid, by="marko", approve=True, comment=""):
    return c.post(
        f"/bank-proposals/{cid}/decision", json={"decided_by": by, "approve": approve, "comment": comment}
    )


def test_iban_check_digits_and_domestic_numbers():
    assert bank.classify("de89 3704 0044 0532 0130 00") == ("iban", IBAN)
    with pytest.raises(ValueError, match="check digits"):
        bank.classify("DE89370400440532013001")
    assert bank.classify("160-0000000012345-61") == ("domestic", "160000000001234561")
    with pytest.raises(ValueError):
        bank.classify("hello")
    with pytest.raises(ValueError):
        bank.classify(" ")


def test_nothing_is_in_force_until_a_different_person_approves(keyed):
    c = keyed
    sid = _supplier(c)
    r = _propose(c, sid)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["current"] is None and v["pending"]["account"] == IBAN and v["pending"]["warnings"] == []
    cid = v["pending"]["id"]
    # the proposer cannot approve, whatever the spelling of the name
    assert _decide(c, cid, by=" KARTEL ").status_code == 409
    assert _decide(c, cid, by="").status_code == 409
    ok = _decide(c, cid)
    assert ok.status_code == 200
    v = ok.json()
    assert (
        v["pending"] is None and v["current"]["account"] == IBAN and v["current"]["confirmed_by"] == "marko"
    )
    assert v["current"]["recent"] and v["history"][0]["status"] == "approved"
    assert _decide(c, cid).status_code == 409  # already decided
    actions = [a.action for a in c.session.query(AuditLog).filter(AuditLog.action.like("bank.%"))]
    assert actions == ["bank.proposed", "bank.approved"]


def test_the_account_is_stored_encrypted_not_as_typed(keyed):
    c = keyed
    sid = _supplier(c)
    cid = _propose(c, sid).json()["pending"]["id"]
    _decide(c, cid)
    for row in (c.session.query(SupplierBankAccount).one(), c.session.query(SupplierBankChange).one()):
        assert IBAN not in row.account_encrypted and len(row.account_hash) == 64


def test_a_change_replaces_the_account_only_when_approved_and_rejection_needs_a_reason(keyed):
    c = keyed
    sid = _supplier(c)
    _decide(c, _propose(c, sid).json()["pending"]["id"])
    # a second proposal while one waits is refused
    first = _propose(c, sid, account=IBAN2, reason="supplier changed bank")
    assert first.status_code == 200 and _propose(c, sid, account=IBAN2).status_code == 409
    cid = first.json()["pending"]["id"]
    assert c.get(f"/suppliers/{sid}/bank").json()["current"]["account"] == IBAN  # old one still in force
    assert _decide(c, cid, approve=False).status_code == 422
    rej = _decide(c, cid, approve=False, comment="the number on the mail does not match the contract")
    v = rej.json()
    assert v["current"]["account"] == IBAN and v["history"][0]["status"] == "rejected"
    # try again and approve: the record is replaced, not duplicated
    cid2 = _propose(c, sid, account=IBAN2, reason="confirmed again").json()["pending"]["id"]
    assert _decide(c, cid2).json()["current"]["account"] == IBAN2
    assert c.session.query(SupplierBankAccount).count() == 1


def test_a_proposal_needs_the_call_to_be_recorded(keyed):
    c = keyed
    sid = _supplier(c)
    assert _propose(c, sid, proposed_by=" ").status_code == 409
    assert _propose(c, sid, callback_by=" ").status_code == 409
    assert _propose(c, sid, callback_person=" ").status_code == 422
    assert _propose(c, sid, callback_source="the mail that asked").status_code == 422
    assert _propose(c, sid, callback_source="other").status_code == 422  # explain where the number came from
    assert _propose(c, sid, callback_source="other", callback_note="phone book").status_code == 200


def test_bad_input_is_refused(keyed):
    c = keyed
    sid = _supplier(c)
    assert _propose(c, sid, account="DE89370400440532013001").status_code == 422
    assert _propose(c, sid, holder=" ").status_code == 422
    assert _propose(c, sid, reason="").status_code == 422
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert _propose(c, sid, callback_on=tomorrow).status_code == 422
    assert _propose(c, sid, swift="123").status_code == 422
    assert c.post("/suppliers/9999/bank/proposals", json=_body()).status_code == 404
    assert _propose(c, sid, swift="deutdeff").json()["pending"]["swift"] == "DEUTDEFF"


def test_withdraw_belongs_to_the_proposer(keyed):
    c = keyed
    sid = _supplier(c)
    cid = _propose(c, sid).json()["pending"]["id"]
    assert c.post(f"/bank-proposals/{cid}/withdraw", params={"by": "marko"}).status_code == 409
    w = c.post(f"/bank-proposals/{cid}/withdraw", params={"by": "kartel"})
    assert (
        w.status_code == 200
        and w.json()["pending"] is None
        and w.json()["history"][0]["status"] == "withdrawn"
    )
    assert _propose(c, sid).status_code == 200  # free again


def test_warnings_for_a_foreign_iban_another_holder_and_a_shared_account(keyed):
    c = keyed
    a = _supplier(c)
    b = _supplier(c, name="Other Parts d.o.o.", country="RS")
    _decide(c, _propose(c, a).json()["pending"]["id"])
    v = _propose(c, b, holder="Someone Else Ltd").json()["pending"]
    text = " | ".join(v["warnings"])
    assert "DE" in text and "RS" in text  # IBAN country against the supplier's country
    assert "Someone Else Ltd" in text and "Acme Elektronik GmbH" in text
    assert "already used by another supplier" in text and "Acme" in text
    # the same account for the same supplier is not a change
    assert _propose(c, a).status_code == 422


def test_recent_changes_age_out_and_pending_list_shows_who_waits(keyed):
    c = keyed
    sid = _supplier(c)
    cid = _propose(c, sid).json()["pending"]["id"]
    pend = c.get("/bank-proposals").json()
    assert pend[0]["supplier"] == "Acme Elektronik GmbH" and pend[0]["proposed_by"] == "kartel"
    _decide(c, cid)
    assert c.get("/bank-proposals").json() == []
    later = date.today() + timedelta(days=bank.RECENT_DAYS + 1)
    cfg = app.dependency_overrides[get_settings]()
    assert bank.view(c.session, cfg, sid, today=date.today())["current"]["recent"] is True
    old = bank.view(c.session, cfg, sid, today=later)["current"]
    assert old["recent"] is False and old["days_in_force"] == bank.RECENT_DAYS + 1
