from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from app.intake.mailbox import EmlDirReader, ImapReader, parse_message


def raw_mail(subject="Упит за понуду", body="Здраво, треба нам 5 штампача.", attach=False) -> bytes:
    msg = EmailMessage()
    msg["From"] = "Милош <milos@example.rs>"
    msg["To"] = "sales@us.example"
    msg["Subject"] = subject
    msg["Message-ID"] = "<abc123@example.rs>"
    msg["Date"] = format_datetime(datetime(2026, 10, 13, 9, 0, tzinfo=UTC))
    msg.set_content(body)
    if attach:
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="spec.pdf")
    return msg.as_bytes()


def test_parse_decodes_cyrillic_headers_and_body():
    mail = parse_message(raw_mail())
    assert mail.subject == "Упит за понуду"
    assert "5 штампача" in mail.body
    assert mail.message_id == "<abc123@example.rs>"
    assert mail.received_at.year == 2026 and mail.received_at.month == 10


def test_parse_takes_text_part_not_attachment():
    mail = parse_message(raw_mail(attach=True))
    assert mail.body.startswith("Здраво")


def test_eml_folder_reader(tmp_path):
    (tmp_path / "a.eml").write_bytes(raw_mail())
    (tmp_path / "ignore.txt").write_text("x")
    assert [m.subject for m in EmlDirReader(tmp_path).fetch_new()] == ["Упит за понуду"]


def test_imap_reader_fetches_unseen_and_logs_out(monkeypatch):
    log = []

    class FakeImap:
        def __init__(self, host, port):
            log.append(("connect", host, port))

        def login(self, u, p):
            log.append(("login", u))

        def select(self, folder):
            log.append(("select", folder))

        def search(self, charset, criterion):
            log.append(("search", criterion))
            return "OK", [b"1 2"]

        def fetch(self, num, spec):
            return "OK", [(b"1 (RFC822 {10}", raw_mail(subject=f"mail {num.decode()}")), b")"]

        def logout(self):
            log.append(("logout",))

    monkeypatch.setattr("app.intake.mailbox.imaplib.IMAP4_SSL", FakeImap)
    mails = list(ImapReader("imap.example", 993, "u", "p").fetch_new())
    assert [m.subject for m in mails] == ["mail 1", "mail 2"]
    assert ("search", "UNSEEN") in log and log[-1] == ("logout",)
