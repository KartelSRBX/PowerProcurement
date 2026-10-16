# 0004. Inbound mail: IMAP in production, `.eml` folder in the demo

Status: accepted (phase 1)

- The plan called for IMAP. Mailpit (the demo inbox) has no IMAP server; `mailpit --help` lists SMTP and POP3 only (checked on v1.31.6).
- `MailboxReader` is the interface. `ImapReader` is for a real mailbox; `EmlDirReader` reads `.eml` files and is what the demo uses.
- `ImapReader` is covered by a unit test with a fake IMAP connection only. It has not been run against a real server; treat it as untested until the deploy phase.
- Readers never send mail. Sending stays in `app/mail/sender.py` behind human approval (ADR 0003).
