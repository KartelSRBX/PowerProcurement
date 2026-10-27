"""Delivery record on a purchase order: promised date, status, delivery date and the history of changes

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("promised_date", sa.Date()))
    op.add_column(
        "purchase_orders",
        sa.Column("delivery_status", sa.String(16), nullable=False, server_default="ordered"),
    )
    op.add_column("purchase_orders", sa.Column("delivered_date", sa.Date()))
    op.create_table(
        "delivery_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("old_value", sa.String(40)),
        sa.Column("new_value", sa.String(40)),
        sa.Column("reason", sa.String(300), nullable=False, server_default=""),
        sa.Column("changed_by", sa.String(128), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("delivery_events")
    op.drop_column("purchase_orders", "delivered_date")
    op.drop_column("purchase_orders", "delivery_status")
    op.drop_column("purchase_orders", "promised_date")
