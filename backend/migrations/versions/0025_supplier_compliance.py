"""Supplier screenings (sanctions list checks), re-check periods and beneficiary records

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_screenings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False, index=True),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("list_name", sa.String(160), nullable=False),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("checked_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "supplier_compliance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False, unique=True),
        sa.Column("period_months", sa.Integer()),
        sa.Column("next_check_on", sa.Date()),
        sa.Column("beneficial_owners", sa.JSON(), nullable=False),
        sa.Column("beneficial_source", sa.String(24)),
        sa.Column("beneficial_note", sa.String(300)),
        sa.Column("beneficial_on", sa.Date()),
        sa.Column("beneficial_by", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("supplier_compliance")
    op.drop_table("supplier_screenings")
