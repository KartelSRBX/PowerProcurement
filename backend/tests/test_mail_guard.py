import pytest

from app.config import Settings
from app.mail.sender import MailSender, OutboundMail, SendRefused


def mail(approved_by="kartel", to="someone@example.com"):
    return OutboundMail(to=to, subject="s", body="b", approved_by=approved_by)


def test_no_approver_no_send():
    with pytest.raises(SendRefused):
        MailSender(Settings(_env_file=None)).send(mail(approved_by=" "))


def test_real_send_requires_allow_list():
    s = Settings(_env_file=None, mail_real_send_enabled=True, mail_allowed_recipients="ok@x.com")
    with pytest.raises(SendRefused, match="not on MAIL_ALLOWED_RECIPIENTS"):
        MailSender(s).send(mail(to="other@x.com"))


def test_default_settings_keep_real_sending_off():
    assert Settings(_env_file=None).mail_real_send_enabled is False


def test_demo_mode_delivers_to_mailpit(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["target"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, msg):
            sent["to"], sent["approved"] = msg["To"], msg["X-Approved-By"]

    monkeypatch.setattr("app.mail.sender.smtplib.SMTP", FakeSMTP)
    s = Settings(_env_file=None, smtp_host="mailpit", smtp_port=1025)
    assert MailSender(s).send(mail()) == "mailpit"
    assert sent == {"target": ("mailpit", 1025), "to": "someone@example.com", "approved": "kartel"}
