"""Savings baseline on a purchase order

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_baselines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False, unique=True),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("amount_eur", sa.Float(), nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("set_by", sa.String(128), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("savings_baselines")
