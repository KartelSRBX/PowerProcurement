"""Getting the text of a legal act into the database: fetch it (EUR-Lex for EU acts, a URL for others) or
read a file a person saved from the official site, then split it into articles.

The app runs on the user's own machine or server, so the fetch uses that machine's network. EUR-Lex
sometimes answers scripts with a browser check instead of the text; the loader says so in plain words and
the same act can then be saved from a browser and uploaded.

Command line: python -m app.legal.loader --fetch eu-2011-7 eu-2016-679
              python -m app.legal.loader --all
              python -m app.legal.loader --dir ./saved   (files named like the keys: eu-2011-7.html, cisg.pdf)"""

# ruff: noqa: E501

import argparse
import hashlib
import io
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.legal.catalog import eurlex_urls
from app.models import AuditLog, LegalProvision, LegalSource

MAX_BYTES = 30_000_000
TIMEOUT = 40.0
UA = "Mozilla/5.0 (compatible; PowerProcurement legal loader)"


class LoadError(Exception):
    """A readable reason the text could not be loaded."""


@dataclass
class Parsed:
    number: str
    heading: str
    text: str


# ---- turning files into text --------------------------------------------------------------------

_BLOCK = {
    "p",
    "div",
    "br",
    "tr",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "section",
    "article",
    "ul",
    "ol",
    "dt",
    "dd",
}
_CELL = {"td", "th"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "noscript"):
            self.skip += 1
        elif tag in _BLOCK:
            self.out.append("\n")
        elif tag in _CELL:
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.out.append("\n")
        elif tag in _CELL:
            self.out.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = "".join(p.out).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except PyPdfError as exc:
        raise LoadError(f"the PDF could not be read ({exc})") from exc


def docx_to_text(data: bytes) -> str:
    import xml.etree.ElementTree as ET
    import zipfile

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise LoadError("the Word file could not be read") from exc
    paras = []
    for p in root.iter(f"{ns}p"):
        paras.append("".join(t.text or "" for t in p.iter(f"{ns}t")))
    return "\n".join(paras)


def to_text(data: bytes, filename: str = "") -> str:
    if len(data) > MAX_BYTES:
        raise LoadError("the file is larger than 30 MB")
    name = filename.lower()
    if name.endswith(".docx") or (data[:2] == b"PK" and b"word/" in data[:4000]):
        text = docx_to_text(data)
    elif name.endswith(".pdf") or data[:5] == b"%PDF-":
        text = pdf_to_text(data)
    else:
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = data.decode("latin-1")
        if name.endswith((".html", ".htm", ".xhtml", ".xml")) or re.search(
            r"<\s*(html|body|p|div)\b", text[:5000], re.I
        ):
            text = html_to_text(text)
    if not text.strip():
        raise LoadError("no text was found in the file (a scan without a text layer cannot be read)")
    return text


# ---- splitting into articles --------------------------------------------------------------------

_ART = re.compile(r"^(?:Article|Art\.|Član|Clanak|Члан)\s*\(?(\d+[a-z]{0,2})\)?\.?\s*(.*)$", re.I)


def parse_provisions(text: str) -> list[Parsed]:
    lines = [ln.strip() for ln in text.splitlines()]
    heads: list[tuple[int, str, str]] = []
    for i, ln in enumerate(lines):
        m = _ART.match(ln)
        if not m:
            continue
        num, rest = m.group(1).lower(), m.group(2).strip(" -–:")
        if rest and (len(rest) > 90 or rest[0].islower() or rest.endswith((".", ";", ","))):
            continue  # a sentence that merely mentions an article
        heads.append((i, num, rest))
    if not heads:
        return [Parsed("text", "Full text", text.strip())]
    parsed: list[Parsed] = []
    pre = "\n".join(ln for ln in lines[: heads[0][0]] if ln).strip()
    if len(pre) > 100:
        parsed.append(Parsed("preamble", "Preamble and recitals", pre))
    for k, (i, num, rest) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = [ln for ln in lines[i + 1 : end] if ln]
        heading = rest
        if not heading and body and len(body[0]) <= 100 and not body[0].endswith((".", ";", ":")):
            heading, body = body[0], body[1:]
        parsed.append(Parsed(num, heading[:300], "\n".join(body).strip()))
    best: dict[str, Parsed] = {}
    order: list[str] = []
    for p in parsed:  # a table of contents repeats the numbers with no body: keep the later one
        if p.number not in best:
            order.append(p.number)
            best[p.number] = p
        elif p.text or not best[p.number].text:
            best[p.number] = (
                p  # the later one is the article itself; the earlier one was in the contents list
            )
    return [best[n] for n in order if best[n].text or best[n].heading]


# ---- fetching -----------------------------------------------------------------------------------


def _challenge(r: httpx.Response) -> bool:
    body = r.text[:4000].lower()
    return r.status_code == 202 or "awswaf" in body or ("javascript" in body and len(r.text) < 4000)


def fetch_text(source: LegalSource, transport: httpx.BaseTransport | None = None) -> str:
    if source.fetch == "eurlex" and source.ref:
        urls = eurlex_urls(source.ref)
    elif source.fetch == "url" and source.source_url:
        urls = [source.source_url]
    else:
        raise LoadError(
            "this act has no download address; save the text from the official site and upload it"
        )
    errors: list[str] = []
    headers = {
        "User-Agent": UA,
        "Accept": "application/xhtml+xml, text/html;q=0.9, application/pdf;q=0.8",
        "Accept-Language": "en",
    }
    with httpx.Client(follow_redirects=True, timeout=TIMEOUT, transport=transport, headers=headers) as client:
        for url in urls:
            try:
                r = client.get(url)
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {type(exc).__name__}")
                continue
            if r.status_code == 403 or r.status_code == 407:
                errors.append(f"{url}: refused ({r.status_code}); the network may block this host")
                continue
            if _challenge(r):
                errors.append(
                    f"{url}: the site asked for a browser check; save the act from a browser and upload it"
                )
                continue
            if r.status_code != 200:
                errors.append(f"{url}: HTTP {r.status_code}")
                continue
            try:
                return to_text(r.content, url)
            except LoadError as exc:
                errors.append(f"{url}: {exc}")
    raise LoadError("; ".join(errors) or "nothing was fetched")


# ---- storing ------------------------------------------------------------------------------------


def store(session: Session, source: LegalSource, text: str, by: str) -> int:
    items = parse_provisions(text)
    session.execute(delete(LegalProvision).where(LegalProvision.source_key == source.key))
    for pos, p in enumerate(items, 1):
        session.add(
            LegalProvision(
                source_key=source.key, position=pos, number=p.number, heading=p.heading, text=p.text
            )
        )
    source.status = "loaded"
    source.provision_count = len(items)
    source.text_hash = hashlib.sha256("\n".join(f"{p.number}|{p.text}" for p in items).encode()).hexdigest()
    source.loaded_at = datetime.now(UTC)
    source.loaded_by = by
    session.add(
        AuditLog(
            actor="human" if by != "loader" else "system",
            actor_id=by,
            action="legal.loaded",
            payload={"source": source.key, "articles": len(items), "hash": source.text_hash[:12]},
        )
    )
    session.commit()
    return len(items)


def load_source(session: Session, key: str, by: str, transport: httpx.BaseTransport | None = None) -> int:
    source = session.get(LegalSource, key)
    if source is None:
        raise LookupError(f"unknown act: {key}")
    return store(session, source, fetch_text(source, transport), by)


def load_file(session: Session, key: str, data: bytes, filename: str, by: str) -> int:
    source = session.get(LegalSource, key)
    if source is None:
        raise LookupError(f"unknown act: {key}")
    return store(session, source, to_text(data, filename), by)


def main(argv: list[str] | None = None) -> int:
    from app.db import get_session
    from app.legal.service import ensure_seed

    ap = argparse.ArgumentParser(description="Load legal acts into the database.")
    ap.add_argument("--fetch", nargs="*", default=[], metavar="KEY")
    ap.add_argument("--all", action="store_true", help="fetch every act that has a download address")
    ap.add_argument("--dir", type=Path, help="folder of saved files named like the act keys")
    ap.add_argument("--by", default="loader")
    args = ap.parse_args(argv)
    session = next(get_session())
    ensure_seed(session)
    keys = list(args.fetch)
    if args.all:
        keys += [
            s.key
            for s in session.scalars(select(LegalSource))
            if s.fetch in ("eurlex", "url") and s.status != "loaded"
        ]
    failed = 0
    for key in keys:
        try:
            print(f"{key}: {load_source(session, key, args.by)} articles")
        except (LoadError, LookupError) as exc:
            failed += 1
            print(f"{key}: FAILED {exc}", file=sys.stderr)
    if args.dir:
        for f in sorted(args.dir.iterdir()):
            if f.is_file() and session.get(LegalSource, f.stem):
                try:
                    print(f"{f.stem}: {load_file(session, f.stem, f.read_bytes(), f.name, args.by)} articles")
                except (LoadError, LookupError) as exc:
                    failed += 1
                    print(f"{f.stem}: FAILED {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
