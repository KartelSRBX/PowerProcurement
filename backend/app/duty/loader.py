"""Load a customs tariff into the duty registry from the command line.

    uv run python -m app.duty.loader --pdf tariff.pdf --source "Customs Tariff 2026" --by Ana \\
        [--rate-date 2026-01-01] [--csv-out tariff.csv]
    uv run python -m app.duty.loader --csv tariff.csv --source "Customs Tariff 2026" --by Ana

The PDF is read page by page and parsed with app.duty.parser; with --csv-out the parsed table is also saved so
the slow reading is done once. Keep the PDF and the table outside the repository."""

import argparse
import sys
from datetime import date
from pathlib import Path

from app.db import get_session
from app.duty import service
from app.duty.parser import DutyLine, parse_lines


def pdf_lines(path: Path) -> list[DutyLine]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = []
    for page in reader.pages:
        text.extend((page.extract_text() or "").splitlines())
    return parse_lines(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", type=Path)
    src.add_argument("--csv", type=Path)
    ap.add_argument(
        "--source",
        required=True,
        help="name of the tariff, for example 'Customs Tariff 2026, Sl. glasnik RS 107/25'",
    )
    ap.add_argument("--rate-date", type=date.fromisoformat, help="date the rates are valid from, YYYY-MM-DD")
    ap.add_argument("--by", required=True, help="who is loading it (recorded)")
    ap.add_argument("--csv-out", type=Path, help="with --pdf: also save the parsed table here")
    args = ap.parse_args()
    lines = pdf_lines(args.pdf) if args.pdf else service.lines_from_csv(args.csv.read_text(encoding="utf-8"))
    if args.csv_out:
        args.csv_out.write_text(service.to_csv(lines), encoding="utf-8")
    session = next(get_session())
    try:
        out = service.import_lines(session, lines, args.source, args.rate_date, args.by)
    except service.DutyError as exc:
        print(f"not loaded: {exc}")
        return 2
    print(
        f"loaded {out['rows']} lines; {out['to_check']} need a look because a rate is not a plain percentage"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
