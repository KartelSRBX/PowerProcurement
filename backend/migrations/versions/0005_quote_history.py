"""quote history for markup analytics

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer", sa.String(length=320), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("cost_eur", sa.Float(), nullable=False),
        sa.Column("markup", sa.Float(), nullable=False),
        sa.Column("price_eur", sa.Float(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("counter_price_eur", sa.Float(), nullable=True),
        sa.Column("quoted_at", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("quote_history")
