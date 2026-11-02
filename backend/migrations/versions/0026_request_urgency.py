"""Request urgency: a flag, a reply-by date and a note, set by a person

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer_requests", sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("customer_requests", sa.Column("respond_by", sa.Date()))
    op.add_column("customer_requests", sa.Column("urgency_note", sa.String(300)))
    op.add_column("customer_requests", sa.Column("urgency_by", sa.String(128)))


def downgrade() -> None:
    op.drop_column("customer_requests", "urgency_by")
    op.drop_column("customer_requests", "urgency_note")
    op.drop_column("customer_requests", "respond_by")
    op.drop_column("customer_requests", "urgent")
