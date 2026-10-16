"""Measures how well the parser reads the gold set of emails.

Run:  uv run python -m app.intake.evaluate            # replay recorded answers
      uv run python -m app.intake.evaluate --live     # call the live model and record answers

The score is deterministic: for each field, exact match against the gold answer. Items are
matched by a keyword that must appear in the description plus an equal quantity.
Numbers are only ever reported from a run that actually happened.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import mean

from app.ai import load_prompt
from app.ai.base import AIAdapter
from app.intake.schemas import ParsedRequest

GOLD_PATH = Path(__file__).parent / "gold" / "intake_gold.json"
PROMPT_ID, PROMPT_VERSION = "intake", "v1"
FIELDS = ["is_request", "language", "category", "budget", "needed_by", "delivery_country"]

_CYR = dict(
    zip(
        "абвгдђежзијклљмнњопрстћуфхцчџш",
        [
            "a",
            "b",
            "v",
            "g",
            "d",
            "đ",
            "e",
            "ž",
            "z",
            "i",
            "j",
            "k",
            "l",
            "lj",
            "m",
            "n",
            "nj",
            "o",
            "p",
            "r",
            "s",
            "t",
            "ć",
            "u",
            "f",
            "h",
            "c",
            "č",
            "dž",
            "š",
        ],
        strict=True,
    )
)


def normalize(text: str) -> str:
    """Lowercase and transliterate Serbian Cyrillic so script choice does not affect matching."""
    return "".join(_CYR.get(ch, ch) for ch in text.lower())


def load_gold(path: Path = GOLD_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def prompt_variables(case: dict) -> dict[str, str]:
    return {
        "received_date": case["received_date"],
        "sender": case["from"],
        "subject": case["subject"],
        "body": case["body"],
    }


def _item_matches(expected: dict, predicted_items: list, used: set[int]) -> int | None:
    for i, p in enumerate(predicted_items):
        if i in used:
            continue
        if normalize(expected["keyword"]) in normalize(p.description) and p.quantity == expected["quantity"]:
            return i
    return None


def score_case(case: dict, parsed: ParsedRequest) -> dict:
    exp = case["expected"]
    field_ok = {
        "is_request": parsed.is_request == exp["is_request"],
        "language": parsed.language == exp["language"],
        "category": parsed.category == exp["category"],
        "budget": (parsed.budget_amount, parsed.budget_currency)
        == (exp["budget_amount"], exp["budget_currency"]),
        "needed_by": parsed.needed_by == (date.fromisoformat(exp["needed_by"]) if exp["needed_by"] else None),
        "delivery_country": parsed.delivery_country == exp["delivery_country"],
    }
    used: set[int] = set()
    matched = 0
    for e in exp["items"]:
        idx = _item_matches(e, parsed.items, used)
        if idx is not None:
            used.add(idx)
            matched += 1
    n_exp, n_pred = len(exp["items"]), len(parsed.items)
    precision = matched / n_pred if n_pred else (1.0 if n_exp == 0 else 0.0)
    recall = matched / n_exp if n_exp else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "id": case["id"],
        "fields": field_ok,
        "item_f1": f1,
        "confidence": parsed.confidence,
        "all_correct": all(field_ok.values()) and f1 == 1.0,
    }


@dataclass
class Report:
    cases: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self, threshold: float) -> dict:
        n = len(self.cases)
        if n == 0:
            return {"cases_scored": 0, "errors": self.errors}
        right = [c["confidence"] for c in self.cases if c["all_correct"]]
        wrong = [c["confidence"] for c in self.cases if not c["all_correct"]]
        return {
            "cases_scored": n,
            "cases_failed_to_run": len(self.errors),
            "field_accuracy": {f: round(mean(c["fields"][f] for c in self.cases), 3) for f in FIELDS},
            "item_f1": round(mean(c["item_f1"] for c in self.cases), 3),
            "fully_correct": f"{len(right)}/{n}",
            "mean_confidence_when_correct": round(mean(right), 3) if right else None,
            "mean_confidence_when_wrong": round(mean(wrong), 3) if wrong else None,
            "sent_to_human_at_threshold": sum(c["confidence"] < threshold for c in self.cases),
            "wrong_but_confident": [
                c["id"] for c in self.cases if not c["all_correct"] and c["confidence"] >= threshold
            ],
            "failed_cases": [c["id"] for c in self.cases if not c["all_correct"]],
        }


def run_eval(adapter: AIAdapter, gold: list[dict] | None = None) -> Report:
    prompt = load_prompt(PROMPT_ID, PROMPT_VERSION)
    report = Report()
    for case in gold or load_gold():
        try:
            result = adapter.extract(prompt, prompt_variables(case), ParsedRequest)
        except Exception as exc:  # noqa: BLE001 - one bad case must not hide the others
            report.errors.append(f"{case['id']}: {type(exc).__name__}: {exc}")
            continue
        report.cases.append(score_case(case, result.parsed))
    return report


def main() -> int:
    from app.ai.factory import RECORDINGS_DIR
    from app.ai.replay import RecordingAdapter, ReplayAdapter
    from app.config import get_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="call the live model and record answers")
    args = parser.parse_args()
    settings = get_settings()
    if args.live:
        from app.ai.anthropic_adapter import AnthropicAdapter

        adapter: AIAdapter = RecordingAdapter(
            AnthropicAdapter(settings.anthropic_api_key, settings.ai_model, settings.ai_max_tokens),
            RECORDINGS_DIR,
        )
    else:
        adapter = ReplayAdapter(RECORDINGS_DIR)
    report = run_eval(adapter)
    print(json.dumps(report.summary(settings.ai_confidence_threshold), indent=2, ensure_ascii=False))
    for err in report.errors:
        print("ERROR", err, file=sys.stderr)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
