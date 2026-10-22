"""Offer lines: a unit price (and minimum order) per requested item

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("request_items.id"), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("moq", sa.Float()),
        sa.UniqueConstraint("offer_id", "item_id"),
    )


def downgrade() -> None:
    op.drop_table("offer_lines")
