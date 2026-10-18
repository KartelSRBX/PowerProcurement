"""AI-assisted steps: supplier replies, follow-up letters, who drafted a letter

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rfqs", sa.Column("drafted_by", sa.String(length=120), nullable=False, server_default="template")
    )
    op.add_column("rfqs", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "customer_quotes",
        sa.Column("drafted_by", sa.String(length=120), nullable=False, server_default="template"),
    )
    op.create_table(
        "supplier_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("customer_requests.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extracted", sa.JSON(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("read_by", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("entered_by", sa.String(length=128), nullable=False),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "letters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("customer_requests.id"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("drafted_by", sa.String(length=120), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("sent_to", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("letters")
    op.drop_table("supplier_replies")
    op.drop_column("customer_quotes", "drafted_by")
    op.drop_column("rfqs", "sent_at")
    op.drop_column("rfqs", "drafted_by")
