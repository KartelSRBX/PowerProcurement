"""Supplier invoice on a purchase order

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False, unique=True),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("total_net", sa.Float(), nullable=False),
        sa.Column("vat_amount", sa.Float()),
        sa.Column("lines", sa.JSON()),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("entered_by", sa.String(128), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("accepted_by", sa.String(128)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("accept_reason", sa.String(300)),
    )


def downgrade() -> None:
    op.drop_table("supplier_invoices")
