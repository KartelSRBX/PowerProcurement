"""create customer_requests

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("message_id", sa.String(255), nullable=False, unique=True),
        sa.Column("sender", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("parsed", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("confirmed_by", sa.String(128)),
        sa.CheckConstraint(
            "status in ('needs_review', 'parsed', 'not_request', 'confirmed')",
            name="customer_requests_status_ck",
        ),
    )


def downgrade() -> None:
    op.drop_table("customer_requests")
