# 0003. Mail leaves the machine only with approval

Status: accepted (phase 0)

- One sender (`MailSender`). A message must carry a non-empty `approved_by`; there is no other send path.
- Default: everything goes to Mailpit. `MAIL_REAL_SEND_ENABLED=false` by default.
- If real sending is enabled, the recipient must also be in `MAIL_ALLOWED_RECIPIENTS`.
- The real SMTP transport is intentionally not implemented in phase 0; enabling the flag fails with a clear error until the deploy phase.
