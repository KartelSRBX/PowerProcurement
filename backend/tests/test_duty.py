"""The duty registry: the parser on an invented sample in the printed layout, the load, the search and the
rates for an origin. No real tariff data is stored in the repository."""

import base64
from datetime import date
from pathlib import Path

import pytest

from app.duty import service
from app.duty.parser import parse_lines
from app.models import AuditLog, DutyRate
from tests.test_pipeline_e2e import SETTINGS, client  # noqa: F401

SAMPLE = Path(__file__).parent / "fixtures" / "duty" / "sample_tariff.txt"


@pytest.fixture
def rows():
    return {r.code: r for r in parse_lines(SAMPLE.read_text(encoding="utf-8").splitlines())}


def test_parser_reads_every_tariff_line_and_skips_headings_headers_and_page_numbers(rows):
    assert sorted(rows) == [
        "9901101000",
        "9901109000",
        "9901201000",
        "9901209010",
        "9902001000",
        "9902009000",
    ]
    a = rows["9901101000"]
    assert (a.unit, a.mfn_rate, a.level) == ("KD", 15.0, 3)
    assert a.description == "прва пробна ставка" and a.heading == "Пробни производи, потпуно измишљени"
    assert (
        a.agreements["SSP"] == 0.0 and a.agreements["CN"] == 9.0 and a.agreements["EG"] == 7.5
    )  # comma decimal
    assert a.agreements["EAEU:AM"] == 0.0 and a.agreements["EFTA:LI"] == 0.0 and "CEFTA" in a.agreements
    assert not a.needs_check


def test_a_wrapped_description_and_a_table_reference_are_kept_as_printed(rows):
    b = rows["9901109000"]
    assert b.description == "друга пробна ставка са дугачким описом који прелази у следећи ред"
    assert b.mfn_rate == 2.5 and b.unit == "-"
    assert b.agreements["SSP"] == "таб. 3" and b.agreements["GB"] == "таб. 6"  # text, not a number
    assert (
        b.agreements["EFTA:IS"] == 10.8
        and b.agreements["EFTA:NO"] == 27.0
        and b.agreements["EFTA:CH"] == "таб. 7"
    )
    assert b.needs_check


def test_a_sub_case_is_noted_and_its_rates_do_not_replace_the_lines_rates(rows):
    c = rows["9901201000"]
    assert c.has_exceptions and "масе преко 80 kg" in c.notes and "остало" in c.notes
    assert c.agreements["GB"] == 0.0 and c.agreements["SSP"] == 0.0  # not 3 or 6 from the sub-cases
    assert c.needs_check


def test_a_line_whose_ssp_cell_is_split_has_cefta_on_the_same_line(rows):
    d = rows["9901209010"]
    assert d.mfn_rate == 20.0 and d.unit == "KD" and "SSP" not in d.agreements
    assert d.agreements["CEFTA"] == 0.0 and d.agreements["TR"] == 20.0 and d.has_exceptions


def test_no_unit_and_specific_duty_cases(rows):
    e = rows["9902001000"]
    assert e.unit == "" and e.mfn_rate == 30.0 and e.description == "пета ставка без јединице"
    f = rows["9902009000"]
    assert f.mfn_rate is None and "min 5,15" in f.mfn_text and f.needs_check  # never converted to a number


def test_csv_round_trip_keeps_everything(rows):
    again = {r.code: r for r in service.lines_from_csv(service.to_csv(list(rows.values())))}
    assert again.keys() == rows.keys()
    assert again["9901109000"].agreements == rows["9901109000"].agreements
    assert again["9902009000"].mfn_rate is None and again["9901201000"].has_exceptions


def test_csv_with_bad_rows_is_refused_with_the_line_number():
    for text, why in (
        ("code,description\n123,x\n", "line 2"),
        ("name\nx\n", "needs at least"),
        ('code,description,mfn_rate,agreements\n9901101000,x,abc,"{}"\n', "line 2"),
        ('code,description,mfn_rate,agreements\n9901101000,x,5,"[1]"\n', "agreements"),
        ('code,description,mfn_rate,agreements\n9901101000,x,5000,"{}"\n', "outside"),
    ):
        with pytest.raises(service.DutyError, match=why):
            service.lines_from_csv(text)


def test_import_replaces_the_registry_and_is_recorded(client, rows):  # noqa: F811
    s = client.session
    lines = list(rows.values())
    out = service.import_lines(s, lines, "Sample tariff", date(2026, 1, 1), "kartel")
    assert out["rows"] == 6 and out["source"] == "Sample tariff" and out["rate_date"] == "2026-01-01"
    assert out["to_check"] == 4  # the lines with a table reference, a sub-case or a specific duty
    out2 = service.import_lines(s, lines[:2], "Second", None, "kartel")
    assert out2["rows"] == 2 and s.query(DutyRate).count() == 2
    events = [a.payload for a in s.query(AuditLog).filter(AuditLog.action == "duties.imported")]
    assert [e["rows"] for e in events] == [6, 2] and events[1]["replaced"] == 6


def test_import_refuses_what_it_cannot_trust(client, rows):  # noqa: F811
    s = client.session
    lines = list(rows.values())
    service.import_lines(s, lines, "Sample", None, "kartel")
    for args, why in (
        ((lines, "Sample", None, " "), "named person"),
        ((lines, " ", None, "kartel"), "which tariff"),
        (([], "Sample", None, "kartel"), "no tariff lines"),
        ((lines + lines[:1], "Sample", None, "kartel"), "twice"),
    ):
        with pytest.raises(service.DutyError, match=why):
            service.import_lines(s, *args)
    assert s.query(DutyRate).count() == 6  # a refused load leaves the registry as it was


def test_api_search_lookup_and_origin_rates(client, rows):  # noqa: F811
    c = client
    assert c.get("/duties/summary").json()["rows"] == 0
    csv_b64 = base64.b64encode(service.to_csv(list(rows.values())).encode()).decode()
    body = {
        "content_base64": csv_b64,
        "source": "Sample tariff",
        "rate_date": "2026-01-01",
        "imported_by": "kartel",
    }
    assert c.post("/duties/import/csv", json={**body, "imported_by": ""}).status_code == 409
    assert c.post("/duties/import/csv", json=body).json()["rows"] == 6
    assert [r["code"] for r in c.get("/duties/search?q=9901 10").json()] == ["9901101000", "9901109000"]
    assert [r["code"] for r in c.get("/duties/search?q=пета").json()] == ["9902001000"]
    assert c.get("/duties/search?q=").json() == []
    one = c.get("/duties/9901.10.10.00?origin=CN").json()
    assert one["code_text"] == "9901 10 10 00" and one["mfn_rate"] == 15.0
    a = one["applicable"]
    assert a["mfn"]["rate"] == 15.0 and a["preferential"] == {"agreement": "CN", "rate": 9.0, "text": "9.0"}
    assert "proof of origin" in " ".join(a["notes"]) and a["source"] == "Sample tariff"
    assert c.get("/duties/0000000000").status_code == 404


def test_origin_countries_map_to_their_agreement(client, rows):  # noqa: F811
    s = client.session
    service.import_lines(s, list(rows.values()), "Sample", None, "kartel")
    row = service.get(s, "9901101000")
    got = {
        o: service.rates_for(row, o)["preferential"]
        for o in ("DE", "RS", "RU", "CH", "BA", "XK", "TR", "US", "")
    }
    assert (
        got["DE"]["agreement"] == "SSP"
        and got["RU"]["agreement"] == "EAEU:RU"
        and got["CH"]["agreement"] == "EFTA:CH"
    )
    assert (
        got["BA"]["agreement"] == "CEFTA"
        and got["XK"]["agreement"] == "CEFTA"
        and got["TR"]["agreement"] == "TR"
    )
    assert got["RS"] is None and got["US"] is None and got[""] is None  # no agreement: the general rate only
    text_row = service.get(s, "9901109000")
    chk = service.rates_for(text_row, "DE")
    assert chk["preferential"]["rate"] is None and chk["needs_check"]
