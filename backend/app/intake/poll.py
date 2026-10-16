"""One polling pass: read new mail, parse it, store it.  uv run python -m app.intake.poll [--dir DIR]"""

import argparse
from pathlib import Path

from app.ai import make_adapter
from app.config import get_settings
from app.db import get_session
from app.intake.mailbox import EmlDirReader, ImapReader, MailboxReader
from app.intake.service import intake_email


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, help="read .eml files from this folder instead of IMAP")
    args = parser.parse_args()
    s = get_settings()
    reader: MailboxReader
    if args.dir:
        reader = EmlDirReader(args.dir)
    elif s.imap_host:
        reader = ImapReader(s.imap_host, s.imap_port, s.imap_user, s.imap_password, s.imap_folder, s.imap_ssl)
    else:
        print("No IMAP_HOST configured and no --dir given.")
        return 2
    session = next(get_session())
    adapter = make_adapter(s)
    for mail in reader.fetch_new():
        row = intake_email(session, adapter, s, mail)
        print(f"{row.id}\t{row.status}\t{row.confidence:.2f}\t{row.subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
