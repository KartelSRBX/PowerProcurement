"""Landed-cost calculation saved per offer; the cost basis kept on a customer quote

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_costs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id"), nullable=False, unique=True),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("goods_eur", sa.Float(), nullable=False),
        sa.Column("landed_cost_eur", sa.Float(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("saved_by", sa.String(128), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "customer_quotes",
        sa.Column("cost_basis", sa.String(16), nullable=False, server_default="flat estimate"),
    )
    op.add_column("customer_quotes", sa.Column("cost_breakdown", sa.JSON()))


def downgrade() -> None:
    op.drop_column("customer_quotes", "cost_breakdown")
    op.drop_column("customer_quotes", "cost_basis")
    op.drop_table("offer_costs")
