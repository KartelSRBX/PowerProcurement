"""Duty registry: customs tariff lines with the general duty and agreement rates

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "duty_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("heading", sa.String(300), nullable=False),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("mfn_rate", sa.Float()),
        sa.Column("mfn_text", sa.String(200), nullable=False),
        sa.Column("agreements", sa.JSON(), nullable=False),
        sa.Column("has_exceptions", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("rate_date", sa.Date()),
        sa.Column("imported_by", sa.String(128), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("duty_rates")
