"""What a person records about an article (manufacturer, end of life, replacements) and the supplier's
authorized brands, repeated back on a request's offers. The code warns; it never decides."""

from datetime import date, timedelta

from app.models import AuditLog, RequestItem, Supplier
from tests.test_comparison import _offer, _setup
from tests.test_pipeline_e2e import client  # noqa: F401


def _note(c, **over):
    body = {"set_by": "kartel", "part_number": "STM32F407VGT6", "brand": "STMicroelectronics", **over}
    return c.put("/articles/notes", json=body)


def _link(c, **over):
    body = {
        "set_by": "kartel",
        "part_number": "STM32F407VGT6",
        "alt_part_number": "STM32F429VGT6",
        "kind": "replacement",
        **over,
    }
    return c.post("/articles/alternates", json=body)


def _request(c, prices=(12, 20)):
    rid, sids, _ = _setup(c)
    first = c.session.query(RequestItem).filter_by(request_id=rid).order_by(RequestItem.id).first()
    first.part_number = (
        "stm32f407-vgt6"  # the same article as STM32F407VGT6 once letters and digits are compared
    )
    c.session.commit()
    offer = _offer(c, rid, sids[0], list(prices))
    return rid, sids, offer


def test_a_record_needs_a_person_something_to_say_and_a_sane_date(client):  # noqa: F811
    c = client
    assert _note(c, set_by=" ").status_code == 409
    assert _note(c, part_number=None, description=None).status_code == 422
    assert _note(c, part_number="--").status_code == 422
    assert _note(c, brand="").status_code == 422  # neither a brand nor an end-of-life mark
    assert _note(c, eol_note="last buy in June").status_code == 422  # a note needs the mark
    future = (date.today() + timedelta(days=5)).isoformat()
    assert _note(c, eol=True, eol_since=future).status_code == 422
    r = _note(c, eol=True, eol_since="2026-03-01", eol_note="last-time buy until June")
    assert r.status_code == 200 and r.json()["eol"] and r.json()["key"] == "pn:stm32f407vgt6"
    # recording again updates the same article, whatever the spelling
    _note(c, part_number="stm32f407 vgt6", brand="ST")
    rows = c.get("/articles/notes").json()["records"]
    assert len(rows) == 1 and rows[0]["brand"] == "ST" and rows[0]["eol"] is False


def test_links_are_checked_and_seen_from_both_sides(client):  # noqa: F811
    c = client
    assert _link(c, set_by=" ").status_code == 409
    assert _link(c, kind="same").status_code == 422
    assert _link(c, alt_part_number="stm32f407-vgt6").status_code == 422  # the same article
    assert _link(c).status_code == 200
    assert _link(c).status_code == 422  # already linked
    assert (
        _link(c, part_number="STM32F429VGT6", alt_part_number="STM32F407VGT6").status_code == 422
    )  # reverse
    from app.suppliers.articles import about

    old = about(c.session, "pn:stm32f407vgt6")["links"][0]
    new = about(c.session, "pn:stm32f429vgt6")["links"][0]
    assert (old["relation"], old["label"]) == ("replaced by", "STM32F429VGT6")
    assert (new["relation"], new["label"]) == ("replaces", "STM32F407VGT6")
    _link(c, part_number="LM358", alt_part_number="LM358N", kind="equivalent")
    assert about(c.session, "pn:lm358")["links"][0]["relation"] == "equivalent"
    assert about(c.session, "pn:lm358n")["links"][0]["relation"] == "equivalent"


def test_an_end_of_life_article_and_its_replacement_show_on_the_request(client):  # noqa: F811
    c = client
    _note(c, eol=True, eol_since="2026-03-01", eol_note="last-time buy until June")
    _link(c)
    rid, sids, offer = _request(c)
    notes = c.get(f"/requests/{rid}/signals").json()["item_notes"]
    assert len(notes) == 1  # only the first item is a known article
    n = notes[0]
    assert n["record"]["eol"] and n["record"]["eol_since"] == "2026-03-01"
    assert n["links"][0]["relation"] == "replaced by" and n["links"][0]["label"] == "STM32F429VGT6"


def test_a_replacement_that_is_itself_end_of_life_is_marked(client):  # noqa: F811
    c = client
    _link(c)
    _note(c, part_number="STM32F429VGT6", brand=None, eol=True)
    from app.suppliers.articles import about

    assert about(c.session, "pn:stm32f407vgt6")["links"][0]["other_eol"] is True


def test_a_supplier_not_marked_authorized_for_the_brand_is_flagged(client):  # noqa: F811
    c = client
    _note(c)  # STMicroelectronics
    rid, sids, offer = _request(c)
    sup = c.session.get(Supplier, sids[0])
    texts = c.get(f"/requests/{rid}/signals").json()["offers"][0]["signals"]
    assert any(
        f"{sup.name} is not marked as an authorized channel for STMicroelectronics" in t for t in texts
    )
    assert any("proof of authorization" in t for t in c.post(f"/requests/{rid}/score").json()[0]["signals"])
    # the person records it: the supplier sells the brand and is authorized for it (case does not matter)
    body = {
        "changed_by": "kartel",
        "changes": {"brands": ["STMicroelectronics"], "authorized_brands": ["stmicroelectronics"]},
    }
    assert c.patch(f"/suppliers/{sids[0]}", json=body).status_code == 200
    assert not [
        t for t in c.get(f"/requests/{rid}/signals").json()["offers"][0]["signals"] if "authorized" in t
    ]


def test_authorized_brands_must_be_brands_the_supplier_sells(client):  # noqa: F811
    c = client
    sid = c.get("/suppliers").json()[0]["id"]
    body = {"changed_by": "kartel", "changes": {"brands": ["Acme"], "authorized_brands": ["Globex"]}}
    r = c.patch(f"/suppliers/{sid}", json=body)
    assert r.status_code == 422 and "Globex" in r.text


def test_an_article_without_a_brand_gets_no_authorization_warning(client):  # noqa: F811
    c = client
    _note(c, brand=None, eol=True)
    rid, sids, offer = _request(c)
    assert not [
        t for t in c.get(f"/requests/{rid}/signals").json()["offers"][0]["signals"] if "authorized" in t
    ]


def test_removing_and_changes_are_logged(client):  # noqa: F811
    c = client
    rec = _note(c).json()
    link = _link(c).json()
    c.delete(f"/articles/alternates/{link['id']}", params={"removed_by": "kartel"})
    r = c.delete(f"/articles/notes/{rec['id']}", params={"removed_by": "kartel"})
    assert r.status_code == 200 and r.json() == {"records": [], "alternates": []}
    assert c.delete(f"/articles/notes/{rec['id']}", params={"removed_by": "kartel"}).status_code == 404
    actions = [
        a.action for a in c.session.query(AuditLog).order_by(AuditLog.id) if a.action.startswith("article.")
    ]
    assert actions == [
        "article.record",
        "article.alternate",
        "article.alternate_removed",
        "article.record_removed",
    ]
