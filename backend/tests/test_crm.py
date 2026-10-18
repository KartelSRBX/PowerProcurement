"""The CRM windows: mail feed, message analytics, supplier storage, article matching, quote preview."""

from tests.test_pipeline_e2e import client, new_request, run_to_offers  # noqa: F401


def test_demo_inbox_is_raw_idempotent_and_linkable(client):  # noqa: F811
    c = client
    assert c.post("/mail/demo-load").json()["added"] == 16
    assert c.post("/mail/demo-load").json()["added"] == 0
    inbox = c.get("/mail", params={"folder": "in"}).json()
    assert len(inbox) == 16 and all(m["status"] == "unparsed" and m["request"] is None for m in inbox)
    assert c.get("/mail", params={"q": "stm32"}).json()

    mail = next(m for m in inbox if "stm32" in m["body"].lower())
    parsed = {
        "is_request": True,
        "language": "en",
        "category": "electronics",
        "confidence": 1.0,
        "items": [{"description": "STM32F407VGT6", "quantity": 500}],
    }
    body = {
        "sender": mail["counterparty"],
        "subject": mail["subject"],
        "body": mail["body"],
        "parsed": parsed,
        "confirmed_by": "kartel",
        "message_id": mail["message_id"],
    }
    rid = c.post("/requests/manual", json=body).json()["id"]
    linked = next(m for m in c.get("/mail", params={"folder": "in"}).json() if m["id"] == mail["id"])
    assert linked["status"] == "confirmed" and linked["request"]["request_id"] == rid
    # the same email cannot become a second request
    assert c.post("/requests/manual", json=body).status_code == 409


def test_outbound_feed_and_analytics_follow_the_pipeline(client):  # noqa: F811
    c = client
    rid = new_request(c)
    run_to_offers(c, rid)
    out = c.get("/mail", params={"folder": "out"}).json()
    assert out and all(m["direction"] == "out" and m["approved_by"] == "kartel" for m in out)
    a = c.get("/analytics/messages").json()
    assert a["totals"]["requests"] == 1 and a["totals"]["outbound_sent"] >= 2
    assert [f["stage"] for f in a["funnel"]][0] == "Emails received"
    assert a["rfq"]["answered"] >= 1 and len(a["volume"]) == 30


def test_supplier_storage_requires_a_named_person_and_is_audited(client):  # noqa: F811
    c = client
    rows = c.get("/suppliers/overview").json()
    assert len(rows) == 12 and all("catalog_lines" in r for r in rows)
    new = {
        "name": "Test Parts d.o.o.",
        "country": "rs",
        "email": "sales@testparts.example",
        "categories": ["electronics"],
        "languages": ["sr"],
        "changed_by": " ",
    }
    assert c.post("/suppliers", json=new).status_code == 409
    new["changed_by"] = "kartel"
    sid = c.post("/suppliers", json=new).json()["id"]
    assert c.post("/suppliers", json=new).status_code == 409  # duplicate name
    detail = c.get(f"/suppliers/{sid}").json()
    assert detail["country"] == "RS" and detail["catalog"] == []
    line = {
        "keyword": "lm358",
        "description": "LM358 dual op-amp",
        "unit_price": 0.2,
        "currency": "EUR",
        "moq": 100,
        "lead_time_days": 5,
        "valid_until": "2027-12-31",
        "changed_by": "kartel",
    }
    assert c.post(f"/suppliers/{sid}/catalog", json=line).status_code == 200
    assert c.post(f"/suppliers/{sid}/catalog", json={**line, "unit_price": -1}).status_code == 422
    assert c.get(f"/suppliers/{sid}").json()["catalog"][0]["source"] == "manual"
    assert (
        c.patch(f"/suppliers/{sid}", json={"changes": {"id": 5}, "changed_by": "kartel"}).status_code == 422
    )
    assert (
        c.patch(
            f"/suppliers/{sid}", json={"changes": {"sanctioned": True}, "changed_by": "kartel"}
        ).status_code
        == 200
    )
    assert c.get(f"/suppliers/{sid}").json()["sanctioned"] is True
    assert c.get("/articles/search", params={"q": "lm358"}).json()[0]["lines"][0]["sanctioned"] is True


def test_article_search_and_request_matching(client):  # noqa: F811
    c = client
    hits = c.get("/articles/search", params={"q": "stm32"}).json()
    assert hits and hits[0]["suppliers"] >= 2 and hits[0]["min_eur"] <= hits[0]["max_eur"]
    assert c.get("/articles/search", params={"q": "nonexistent-part"}).json() == []
    rid = new_request(c)
    items = c.get(f"/requests/{rid}/articles").json()
    assert len(items) == 2 and all(i["matches"] for i in items)
    line = items[0]["matches"][0]["lines"][0]
    assert "moq_ok" in line and line["line_total_eur"] > 0
    assert c.get("/requests/9999/articles").status_code == 404


def test_quote_preview_matches_the_real_quote(client):  # noqa: F811
    c = client
    rid = new_request(c)
    run_to_offers(c, rid)
    ranked = c.post(f"/requests/{rid}/score").json()
    best = next(r for r in ranked if not r["excluded"])
    prev = c.get(
        f"/requests/{rid}/quote-preview",
        params={"offer_id": best["offer_id"], "markup": 0.15, "currency": "RSD"},
    ).json()
    quote = c.post(
        f"/requests/{rid}/quotes",
        json={"offer_id": best["offer_id"], "markup": 0.15, "currency": "RSD", "created_by": "kartel"},
    ).json()
    assert prev["price"] == quote["price"] and prev["landed_cost_eur"] == quote["cost_eur"]
    assert prev["below_cost"] is False and prev["margin_eur"] > 0
    below = c.get(
        f"/requests/{rid}/quote-preview",
        params={"offer_id": best["offer_id"], "markup": -0.1, "currency": "EUR"},
    ).json()
    assert below["below_cost"] is True
    assert c.get("/config").json()["default_markup"] == 0.15


GOOD_CSV = (
    "keyword,description,unit_price,currency,moq,lead_time_days,valid_until\n"
    "lm358,LM358 dual op-amp,0.21,EUR,100,5,2099-12-31\n"
    "NE555, NE555 timer ,0.18,eur,100,4,2099-12-31\n"
)


def _new_supplier(c):
    r = c.post(
        "/suppliers",
        json={"name": "CSV Parts", "country": "RS", "email": "a@b.example", "changed_by": "kartel"},
    )
    return r.json()["id"]


def test_csv_import_preview_writes_nothing_and_apply_is_audited(client):  # noqa: F811
    c = client
    sid = _new_supplier(c)
    url = f"/suppliers/{sid}/catalog/import"
    prev = c.post(url, json={"csv": GOOD_CSV, "changed_by": "kartel", "dry_run": True}).json()
    assert prev["total"] == 2 and prev["invalid"] == 0 and prev["to_add"] == 2 and not prev["applied"]
    assert c.get(f"/suppliers/{sid}").json()["catalog"] == []
    assert c.post(url, json={"csv": GOOD_CSV, "changed_by": " ", "dry_run": False}).status_code == 409
    done = c.post(url, json={"csv": GOOD_CSV, "changed_by": "kartel", "dry_run": False}).json()
    assert done["applied"] is True
    cat = {r["keyword"]: r for r in c.get(f"/suppliers/{sid}").json()["catalog"]}
    assert set(cat) == {"lm358", "ne555"} and cat["ne555"]["currency"] == "EUR"
    assert cat["lm358"]["source"] == "csv-import"
    # a second file with the same keyword refreshes the price instead of duplicating the line
    again = GOOD_CSV.replace("0.21", "0.25")
    r = c.post(url, json={"csv": again, "changed_by": "kartel", "dry_run": False}).json()
    assert r["to_update"] == 2 and r["to_add"] == 0
    cat = c.get(f"/suppliers/{sid}").json()["catalog"]
    assert len(cat) == 2 and next(x for x in cat if x["keyword"] == "lm358")["unit_price"] == 0.25


def test_csv_import_is_all_or_nothing_and_explains_each_error(client):  # noqa: F811
    c = client
    sid = _new_supplier(c)
    url = f"/suppliers/{sid}/catalog/import"
    bad = (
        "keyword;description;price;currency;lead_time;valid_until\n"
        "ok1;Fine part;1,5;EUR;3;2099-01-01\n"
        "ok1;Same key again;1,5;EUR;3;2099-01-01\n"
        ";No key;2;EUR;3;2099-01-01\n"
        "x3;Bad price;abc;EUR;3;2099-01-01\n"
        "x4;Bad cur;1;GBP;3;2099-01-01\n"
        "x5;Old;1;EUR;3;2001-01-01\n"
    )
    prev = c.post(url, json={"csv": bad, "changed_by": "kartel", "dry_run": True}).json()
    assert prev["total"] == 6 and prev["invalid"] == 5 and prev["rows"][0]["data"]["unit_price"] == 1.5
    problems = " ".join(e for r in prev["rows"] for e in r["errors"])
    for word in (
        "duplicate keyword",
        "keyword is empty",
        "not a number",
        "currency must be",
        "already expired",
    ):
        assert word in problems
    assert c.post(url, json={"csv": bad, "changed_by": "kartel", "dry_run": False}).status_code == 409
    assert c.get(f"/suppliers/{sid}").json()["catalog"] == []


def test_csv_import_rejects_unusable_files(client):  # noqa: F811
    c = client
    sid = _new_supplier(c)
    url = f"/suppliers/{sid}/catalog/import"
    for text in (
        "",
        "keyword,description\nx,y\n",
        "keyword,description,unit_price,currency,lead_time_days,valid_until\n",
    ):
        assert c.post(url, json={"csv": text, "changed_by": "kartel"}).status_code == 422
    assert (
        c.post("/suppliers/9999/catalog/import", json={"csv": GOOD_CSV, "changed_by": "k"}).status_code == 404
    )
