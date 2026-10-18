"""One purchase order per request, enforced by the database

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_purchase_orders_request_id", "purchase_orders", ["request_id"])


def downgrade() -> None:
    op.drop_constraint("uq_purchase_orders_request_id", "purchase_orders", type_="unique")
