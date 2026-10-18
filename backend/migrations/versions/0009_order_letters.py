"""Letters can belong to a purchase order (order confirmation, delivery question)

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "letters", sa.Column("order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("letters", "order_id")
