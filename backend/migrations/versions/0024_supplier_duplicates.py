"""Supplier tax number and reviews of possible duplicate suppliers

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("tax_id", sa.String(40)))
    op.create_table(
        "supplier_duplicate_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_a_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("supplier_b_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("verdict", sa.String(12), nullable=False),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("supplier_a_id", "supplier_b_id"),
    )


def downgrade() -> None:
    op.drop_table("supplier_duplicate_reviews")
    op.drop_column("suppliers", "tax_id")
