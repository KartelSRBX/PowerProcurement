"""Inbound mail: the reading made from it

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inbox_emails", sa.Column("reply_id", sa.Integer(), sa.ForeignKey("supplier_replies.id")))


def downgrade() -> None:
    op.drop_column("inbox_emails", "reply_id")
