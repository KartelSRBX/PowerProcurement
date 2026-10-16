from datetime import date

from app.ai import load_prompt
from app.ai.base import AIResult
from app.intake.evaluate import load_gold, normalize, prompt_variables, run_eval, score_case
from app.intake.schemas import ParsedRequest, RequestItem

GOLD = load_gold()


def oracle(case: dict, **overrides) -> ParsedRequest:
    e = case["expected"]
    data = {
        "is_request": e["is_request"],
        "language": e["language"],
        "category": e["category"],
        "items": [
            RequestItem(description=f"{i['keyword']} item", quantity=i["quantity"]) for i in e["items"]
        ],
        "budget_amount": e["budget_amount"],
        "budget_currency": e["budget_currency"],
        "needed_by": date.fromisoformat(e["needed_by"]) if e["needed_by"] else None,
        "delivery_country": e["delivery_country"],
        "confidence": 0.9,
    }
    data.update(overrides)
    return ParsedRequest(**data)


class OracleAdapter:
    """Answers every gold email with its gold answer: proves the harness scores a perfect parser 100%."""

    def extract(self, prompt, variables, schema):
        case = next(c for c in GOLD if c["body"] == variables["body"])
        return AIResult(oracle(case), "oracle", prompt.id, prompt.version)


def test_gold_set_is_consistent():
    assert len(GOLD) >= 16
    assert len({c["id"] for c in GOLD}) == len(GOLD)
    langs = {c["expected"]["language"] for c in GOLD}
    assert langs == {"sr", "en", "other"}
    assert sum(not c["expected"]["is_request"] for c in GOLD) >= 2
    assert any("ћ" in c["body"] or "ш" in c["body"] for c in GOLD)  # at least one Cyrillic email
    for c in GOLD:
        for item in c["expected"]["items"]:
            assert normalize(item["keyword"]) in normalize(c["body"]), (c["id"], item)


def test_every_gold_email_renders_into_the_prompt():
    prompt = load_prompt("intake", "v1")
    for c in GOLD:
        text = prompt.render(prompt_variables(c))
        assert c["body"] in text and c["received_date"] in text


def test_perfect_parser_scores_100_percent():
    report = run_eval(OracleAdapter())
    summary = report.summary(0.75)
    assert summary["fully_correct"] == f"{len(GOLD)}/{len(GOLD)}"
    assert summary["item_f1"] == 1.0 and not report.errors


def test_wrong_quantity_and_extra_item_are_penalised():
    case = next(c for c in GOLD if c["id"] == "en-01-mcu-passives")
    wrong_qty = oracle(
        case,
        items=[
            RequestItem(description="STM32F407VGT6", quantity=50),
            RequestItem(description="100nF capacitor", quantity=2000),
        ],
    )
    assert score_case(case, wrong_qty)["item_f1"] == 0.5
    extra = oracle(case)
    extra.items.append(RequestItem(description="something invented", quantity=1))
    assert 0.5 < score_case(case, extra)["item_f1"] < 1.0


def test_wrong_field_makes_case_not_fully_correct():
    case = next(c for c in GOLD if c["id"] == "en-02-laptops")
    scored = score_case(case, oracle(case, budget_currency="USD"))
    assert scored["fields"]["budget"] is False and scored["all_correct"] is False


def test_cyrillic_and_latin_spelling_match_the_same_keyword():
    case = next(c for c in GOLD if c["id"] == "sr-13-kondenzatori-cir")
    latin = oracle(
        case,
        items=[
            RequestItem(description="Kondenzatori 10µF", quantity=5000),
            RequestItem(description="Otpornici 10kΩ", quantity=2000),
        ],
    )
    assert score_case(case, latin)["item_f1"] == 1.0


def test_a_failing_case_is_reported_not_hidden():
    class Boom:
        def extract(self, *a):
            raise RuntimeError("api down")

    report = run_eval(Boom())
    assert len(report.errors) == len(GOLD) and report.summary(0.75)["cases_scored"] == 0
