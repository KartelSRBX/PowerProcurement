"""The only way mail leaves the application.

- A message needs a named human approver; there is no code path that sends without one.
- In demo mode (default) every message goes to Mailpit, whatever the recipient.
- With real sending enabled, recipients must also be on the allow-list.
"""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.config import Settings


class SendRefused(Exception):
    pass


@dataclass(frozen=True)
class OutboundMail:
    to: str
    subject: str
    body: str
    approved_by: str
    message_id: str | None = None  # lets a reply be matched to the letter it answers


class MailSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, mail: OutboundMail) -> str:
        """Returns where the message went: 'mailpit' or 'smtp'."""
        if not mail.approved_by.strip():
            raise SendRefused("outbound mail needs a human approver")
        s = self.settings
        if s.mail_real_send_enabled and mail.to.lower() not in s.allowed_recipients:
            raise SendRefused(f"{mail.to} is not on MAIL_ALLOWED_RECIPIENTS")
        if s.mail_real_send_enabled:
            raise SendRefused("real SMTP transport is not implemented yet (planned for the deploy phase)")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.mail_from, mail.to, mail.subject
        msg["X-Approved-By"] = mail.approved_by
        if mail.message_id:
            msg["Message-ID"] = mail.message_id
        msg.set_content(mail.body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)
        return "mailpit"
