"""Where incoming emails come from. Reading is read-only with respect to the outside world:
no adapter here can send anything."""

import email
import imaplib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class InboundEmail:
    message_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime


class MailboxReader(Protocol):
    def fetch_new(self) -> Iterator[InboundEmail]: ...


def _decode(value: str | None) -> str:
    return str(make_header(decode_header(value))) if value else ""


def _text_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return _payload_text(part)
        return ""
    return _payload_text(msg)


def _payload_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()


def parse_message(raw: bytes) -> InboundEmail:
    msg = email.message_from_bytes(raw)
    try:
        received = parsedate_to_datetime(msg["Date"])
    except (TypeError, ValueError):
        received = datetime.now(UTC)
    return InboundEmail(
        message_id=(msg["Message-ID"] or "").strip(),
        sender=_decode(msg["From"]),
        subject=_decode(msg["Subject"]),
        body=_text_body(msg),
        received_at=received,
    )


class EmlDirReader:
    """Demo source: .eml files in a folder. Used because Mailpit speaks SMTP/POP3, not IMAP."""

    def __init__(self, directory: Path):
        self.directory = directory

    def fetch_new(self) -> Iterator[InboundEmail]:
        for path in sorted(self.directory.glob("*.eml")):
            yield parse_message(path.read_bytes())


class ImapReader:
    """Reads UNSEEN messages from an IMAP mailbox. Not yet exercised against a real server."""

    def __init__(
        self, host: str, port: int, user: str, password: str, folder: str = "INBOX", ssl: bool = True
    ):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.folder, self.ssl = folder, ssl

    def fetch_new(self) -> Iterator[InboundEmail]:
        cls = imaplib.IMAP4_SSL if self.ssl else imaplib.IMAP4
        conn = cls(self.host, self.port)
        try:
            conn.login(self.user, self.password)
            conn.select(self.folder)
            _, data = conn.search(None, "UNSEEN")
            for num in data[0].split():
                _, parts = conn.fetch(num, "(RFC822)")
                yield parse_message(parts[0][1])
        finally:
            try:
                conn.logout()
            except imaplib.IMAP4.error:
                pass
