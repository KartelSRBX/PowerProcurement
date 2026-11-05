"""Checklist progress: where a person stands on each line of the CBAM and e-invoice lists

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checklist_progress",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("set_by", sa.String(128), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("checklist_progress")
