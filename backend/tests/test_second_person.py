"""A second person by risk: an order that meets a switched-on rule is created only when a different person
confirms it. The rules are the company's to set; all are off until then."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app import config
from app.config import get_settings, set_overrides
from app.main import app
from app.models import AuditLog, Contract, ContractFinding, PurchaseOrder, SecondApproval, SupplierBankChange
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401


@pytest.fixture
def c(client):  # noqa: F811
    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(update=dict(config._overrides))
    yield client
    set_overrides({})


def _accepted(c, supplier_index=0):
    """A request whose customer accepted a quote, ready for its order. Returns (request id, supplier id)."""
    rid, sids, _ = _setup(c)
    a = _offer(c, rid, sids[supplier_index], [10, 20], incoterm="DAP", incoterm_place="Belgrade")
    q = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": a["id"], "markup": 0.2, "currency": "EUR", "created_by": "kartel"},
    ).json()
    c.post(f"/quotes/{q['id']}/decision", json={"approve": True, "decided_by": "kartel"})
    c.post(f"/quotes/{q['id']}/outcome", json={"kind": "accepted", "confirmed_by": "kartel"})
    return rid, sids[supplier_index]


def _rules(c, over_eur=0, new_supplier=False, bank_days=0, legal_red=False, by="kartel"):
    r = c.put(
        "/settings/second",
        json={
            "changed_by": by,
            "over_eur": over_eur,
            "new_supplier": new_supplier,
            "bank_days": bank_days,
            "legal_red": legal_red,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _order(c, rid, by="anna"):
    return c.post(f"/requests/{rid}/orders", json={"approved_by": by})


def _confirm(c, rid, by="boris", approve=True, comment=""):
    return c.post(
        f"/requests/{rid}/second-approval", json={"decided_by": by, "approve": approve, "comment": comment}
    )


def test_all_rules_are_off_until_the_company_sets_them(c):
    s = c.get("/settings").json()["second"]
    assert s == {"over_eur": 0, "new_supplier": False, "bank_days": 0, "legal_red": False}
    rid, _ = _accepted(c)
    assert c.get(f"/requests/{rid}/order-risks").json()["risks"] == []
    r = _order(c, rid)
    assert r.status_code == 200 and r.json()["second_by"] is None


def test_settings_are_validated_and_logged(c):
    assert _rules(c, over_eur=5000, new_supplier=True, bank_days=30, legal_red=True)["second"] == {
        "over_eur": 5000,
        "new_supplier": True,
        "bank_days": 30,
        "legal_red": True,
    }
    bad = c.put(
        "/settings/second",
        json={"changed_by": "x", "over_eur": -1, "new_supplier": False, "bank_days": 0, "legal_red": False},
    )
    assert bad.status_code == 422
    assert c.session.query(AuditLog).filter(AuditLog.action == "settings.update").count() >= 1


def test_a_large_total_needs_a_second_person_who_is_not_the_first(c):
    rid, _ = _accepted(c)
    _rules(c, over_eur=1)
    risks = c.get(f"/requests/{rid}/order-risks").json()["risks"]
    assert [r["kind"] for r in risks] == ["large_sum"] and "above 1.00 EUR" in risks[0]["text"]

    first = _order(c, rid, "anna")
    assert first.status_code == 202 and first.json()["needs_second_person"] is True
    assert "second person" in first.json()["detail"] and first.json()["pending"]["requested_by"] == "anna"
    assert c.session.query(PurchaseOrder).count() == 0 and c.outbox[-1]["subject"] != "PO"
    sent_before = len(c.outbox)

    same = _confirm(c, rid, "Anna")  # the first approver cannot be the second, whatever the case
    assert same.status_code == 409 and "different person" in same.json()["detail"]
    assert c.session.query(PurchaseOrder).count() == 0 and len(c.outbox) == sent_before

    done = _confirm(c, rid, "boris", comment="checked the price")
    assert done.status_code == 200
    po = done.json()
    assert po["approved_by"] == "anna" and po["second_by"] == "boris" and po["status"] == "sent"
    assert len(c.outbox) == sent_before + 1 and c.outbox[-1]["approved_by"] == "anna"
    row = c.session.query(SecondApproval).one()
    assert (row.status, row.decided_by, row.comment) == ("confirmed", "boris", "checked the price")
    actions = [a.action for a in c.session.query(AuditLog).filter(AuditLog.action.like("po.%"))]
    assert "po.second_confirmed" in actions and "po.approved" in actions
    assert _order(c, rid, "carl").status_code == 409  # one order per request
    assert _confirm(c, rid, "dora").status_code == 404  # nothing waits any more


def test_a_rejection_needs_a_reason_and_creates_no_order(c):
    rid, _ = _accepted(c)
    _rules(c, over_eur=1)
    assert _order(c, rid).status_code == 202
    assert _confirm(c, rid, approve=False).status_code == 422
    r = _confirm(c, rid, approve=False, comment="price looks wrong")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert c.session.query(PurchaseOrder).count() == 0
    # the first approver can ask again; that is a new ask, and the old one stays as history
    assert _order(c, rid).status_code == 202
    assert [x["status"] for x in c.get("/second-approvals?status=all").json()] == ["pending", "rejected"]
    assert len(c.get("/second-approvals").json()) == 1


def test_asking_again_renews_the_waiting_ask_and_the_new_asker_cannot_confirm_it(c):
    rid, _ = _accepted(c)
    _rules(c, over_eur=1)
    _order(c, rid, "anna")
    _order(c, rid, "carl")
    pending = c.get("/second-approvals").json()
    assert len(pending) == 1 and pending[0]["requested_by"] == "carl"
    assert _confirm(c, rid, "carl").status_code == 409
    done = _confirm(c, rid, "anna")  # now anna is the other person
    assert (
        done.status_code == 200
        and done.json()["approved_by"] == "carl"
        and done.json()["second_by"] == "anna"
    )


def test_a_supplier_without_a_delivered_order_is_new(c):
    rid, sid = _accepted(c)
    _rules(c, new_supplier=True)
    assert [r["kind"] for r in c.get(f"/requests/{rid}/order-risks").json()["risks"]] == ["new_supplier"]
    assert _order(c, rid).status_code == 202
    po = _confirm(c, rid).json()
    # once that order is delivered the supplier is no longer new for the next request
    c.put(f"/orders/{po['id']}/delivery", json={"changed_by": "kartel", "status": "delivered"})
    rid2, sid2 = _accepted(c)
    assert sid2 == sid  # the same supplier, now with a delivered order
    assert c.get(f"/requests/{rid2}/order-risks").json()["risks"] == []
    rid3, sid3 = _accepted(c, supplier_index=1)
    assert sid3 != sid  # another supplier with nothing delivered is still new
    assert [r["kind"] for r in c.get(f"/requests/{rid3}/order-risks").json()["risks"]] == ["new_supplier"]


def test_a_recent_bank_change_needs_a_second_person_until_it_is_old_enough(c):
    rid, sid = _accepted(c)
    c.session.add(
        SupplierBankChange(
            supplier_id=sid, account_encrypted="x", account_hash="h", kind="iban", holder="H", reason="r",
            proposed_by="p", callback_by="p", callback_person="q", callback_source="contract",
            callback_on=date.today(), status="approved", decided_by="d",
            decided_at=datetime.now(UTC) - timedelta(days=10),
        )
    )  # fmt: skip
    c.session.commit()
    _rules(c, bank_days=7)
    assert c.get(f"/requests/{rid}/order-risks").json()["risks"] == []  # 10 days ago is outside 7
    _rules(c, bank_days=30)
    risks = c.get(f"/requests/{rid}/order-risks").json()["risks"]
    assert [r["kind"] for r in risks] == ["bank_changed"] and "within 30 days" in risks[0]["text"]
    _rules(c, bank_days=0)
    assert c.get(f"/requests/{rid}/order-risks").json()["risks"] == []


def test_an_open_red_legal_remark_needs_a_second_person(c):
    rid, _ = _accepted(c)
    contract = Contract(
        title="Supply", counterparty="X", role="buy", request_id=rid, text="t", text_hash="h", created_by="k"
    )
    c.session.add(contract)
    c.session.flush()
    finding = ContractFinding(
        contract_id=contract.id, rule_key="k", severity="red", title="Unlimited liability", state="open"
    )
    c.session.add(finding)
    c.session.commit()
    _rules(c, legal_red=True)
    assert [r["kind"] for r in c.get(f"/requests/{rid}/order-risks").json()["risks"]] == ["legal_red"]
    assert _order(c, rid).status_code == 202
    finding.state = "accepted"  # a person dealt with it
    c.session.commit()
    assert c.get(f"/requests/{rid}/order-risks").json()["risks"] == []


def test_several_rules_are_listed_together_and_a_met_rule_never_changes_a_score(c):
    rid, _ = _accepted(c)
    _rules(c, over_eur=1, new_supplier=True)
    kinds = [r["kind"] for r in c.get(f"/requests/{rid}/order-risks").json()["risks"]]
    assert kinds == ["large_sum", "new_supplier"]
    before = c.get(f"/requests/{rid}/comparison").json()
    _order(c, rid)
    assert c.get(f"/requests/{rid}/comparison").json() == before


def test_the_status_filter_is_checked(c):
    assert c.get("/second-approvals?status=nonsense").status_code == 422


def test_the_today_page_lists_orders_waiting_for_a_second_person(c):
    rid, _ = _accepted(c)
    _rules(c, over_eur=1)
    _order(c, rid, "anna")
    sec = next(s for s in c.get("/summary/today").json()["sections"] if s["key"] == "orders")
    assert sec["count"] == 1 and "approved by anna" in sec["items"][0]["text"]
    _confirm(c, rid, "boris")
    sec = next(s for s in c.get("/summary/today").json()["sections"] if s["key"] == "orders")
    assert sec["count"] == 0
