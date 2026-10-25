"""The landed-cost arithmetic, recalculated by hand in each case. Pure code: no database."""

import pytest

from app.legal.incoterms import CODES
from app.pricing.landed import COVERED, LandedInput, compute

A = pytest.approx


def test_ex_works_adds_everything_the_seller_left_out():
    r = compute(
        LandedInput(
            1000, "EXW", origin_eur=50, freight_eur=120, insurance_pct=0.5, inland_eur=30, clearance_eur=40,
            duty_pct=10, vat_pct=20,
        )
    )  # fmt: skip
    # insurance 0.5% of 1000+50+120 = 5.85; customs value 1000+50+120+5.85 = 1175.85; duty 117.585
    # VAT base 1175.85+117.585+40+30 = 1363.435; VAT 20% = 272.687
    assert r.customs_value_eur == A(1175.85) and r.duty_eur == A(117.585)
    assert r.vat_base_eur == A(1363.435) and r.vat_eur == A(272.687)
    assert r.landed_cost_eur == A(1363.435)  # VAT is reclaimable, so it is not a cost
    assert r.cash_out_eur == A(1636.122) and r.complete and not r.warnings
    assert {ln.key for ln in r.lines} == {
        "goods",
        "origin",
        "carriage",
        "insurance",
        "duty",
        "clearance",
        "inland",
        "vat",
    }


def test_vat_that_cannot_be_reclaimed_is_part_of_the_cost():
    r = compute(
        LandedInput(
            1000, "EXW", origin_eur=50, freight_eur=120, insurance_pct=0.5, inland_eur=30, clearance_eur=40,
            duty_pct=10, vat_pct=20, vat_recoverable=False,
        )
    )  # fmt: skip
    assert r.landed_cost_eur == A(1636.122) == r.cash_out_eur


def test_cif_already_has_carriage_and_insurance_so_only_import_costs_are_added():
    r = compute(LandedInput(1000, "CIF", inland_eur=30, clearance_eur=40, duty_pct=5, vat_pct=20))
    # customs value 1000; duty 50; VAT base 1000+50+40+30 = 1120; VAT 224
    assert r.customs_value_eur == 1000 and r.duty_eur == A(50) and r.vat_base_eur == A(1120)
    assert r.landed_cost_eur == A(1120) and r.cash_out_eur == A(1344) and r.complete
    assert r.included_by_seller == ["origin charges", "main carriage", "insurance"]


def test_cfr_leaves_insurance_to_the_buyer():
    r = compute(
        LandedInput(1000, "CFR", insurance_pct=1, inland_eur=0, clearance_eur=0, duty_pct=10, vat_pct=20)
    )  # fmt: skip
    # insurance 1% of 1000 = 10; customs value 1010; duty 101; landed 1111; VAT 20% of 1111 = 222.2
    assert r.customs_value_eur == A(1010) and r.duty_eur == A(101)
    assert r.landed_cost_eur == A(1111) and r.vat_eur == A(222.2) and r.cash_out_eur == A(1333.2)


def test_fob_leaves_carriage_and_insurance_to_the_buyer_and_a_zero_duty_adds_nothing():
    r = compute(
        LandedInput(
            2000, "FOB", freight_eur=200, insurance_eur=12, inland_eur=70, clearance_eur=50,
            duty_pct=0, vat_pct=20,
        )
    )  # fmt: skip
    # customs value 2000+200+12 = 2212, no duty; VAT base 2212+50+70 = 2332; VAT 466.4
    assert r.customs_value_eur == A(2212) and r.duty_eur == 0
    assert r.landed_cost_eur == A(2332) and r.vat_eur == A(466.4) and r.cash_out_eur == A(2798.4)


def test_dap_customs_value_leaves_out_transport_after_the_border():
    r = compute(LandedInput(1000, "DAP", inland_in_price_eur=80, clearance_eur=25, duty_pct=10, vat_pct=20))
    # customs value 1000-80 = 920; duty 92; VAT base 920+92+25 = 1037; VAT 207.4
    assert r.customs_value_eur == A(920) and r.duty_eur == A(92) and r.vat_base_eur == A(1037)
    assert r.landed_cost_eur == A(1117) and r.cash_out_eur == A(1324.4)
    assert not any("after the border" in w for w in r.warnings)


def test_dap_without_the_inland_share_warns_that_the_customs_value_may_be_too_high():
    r = compute(LandedInput(1000, "DAP", clearance_eur=25, duty_pct=10, vat_pct=20))
    assert r.customs_value_eur == 1000 and any("after the border" in w for w in r.warnings)


def test_ddp_needs_no_import_figures_and_says_who_pays_the_taxes():
    r = compute(LandedInput(1000, "DDP"))
    assert r.landed_cost_eur == 1000 == r.cash_out_eur and r.duty_eur == 0 and r.vat_eur == 0 and r.complete
    assert any("DDP" in w for w in r.warnings)


def test_missing_figures_are_reported_and_the_result_is_marked_incomplete():
    r = compute(LandedInput(500, "EXW"))
    assert not r.complete and r.landed_cost_eur == 500
    text = " | ".join(r.warnings)
    for part in (
        "origin charges",
        "main carriage",
        "insurance",
        "duty rate",
        "customs agent",
        "inside the country",
        "VAT rate",
    ):
        assert part in text, part


def test_no_incoterms_rule_is_treated_as_ex_works_with_a_warning():
    r = compute(
        LandedInput(
            500,
            None,
            origin_eur=10,
            freight_eur=20,
            insurance_eur=1,
            inland_eur=2,
            clearance_eur=3,
            duty_pct=0,
            vat_pct=20,
        )
    )
    assert r.complete and any("no Incoterms rule" in w for w in r.warnings)
    assert r.landed_cost_eur == A(500 + 10 + 20 + 1 + 2 + 3)


def test_bad_input_is_refused():
    for kw, why in (
        ({"price_eur": 0}, "above zero"),
        ({"price_eur": 10, "freight_eur": -1}, "negative"),
        ({"price_eur": 10, "incoterm": "XYZ"}, "unknown Incoterms"),
        ({"price_eur": 10, "incoterm": "DAP", "inland_in_price_eur": 11}, "more than the price"),
    ):
        with pytest.raises(ValueError, match=why):
            compute(LandedInput(**kw))


def test_every_incoterms_rule_is_covered_and_more_included_never_means_more_to_add():
    assert set(COVERED) == set(CODES)
    chain = ["EXW", "FCA", "CFR", "CIF", "DAP", "DDP"]
    counts = [sum(COVERED[c]) for c in chain]
    assert counts == sorted(counts) and counts[0] == 0 and counts[-1] == 5
    # the same goods, every rule given the same figures: the buyer-added part only shrinks along the chain
    kw = dict(
        origin_eur=50,
        freight_eur=100,
        insurance_eur=10,
        inland_eur=20,
        clearance_eur=30,
        duty_pct=10,
        vat_pct=20,
    )
    added = [compute(LandedInput(1000, c, **kw)).landed_cost_eur - 1000 for c in chain]
    assert added == sorted(added, reverse=True)
