"""Second person by risk: the asks, and who was the second person on an order

Revision ID: 0029
Revises: 0028
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("second_by", sa.String(128), nullable=True))
    op.create_table(
        "second_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("customer_requests.id"), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.String(300), nullable=True),
    )
    op.create_index("ix_second_approvals_request_id", "second_approvals", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_second_approvals_request_id", table_name="second_approvals")
    op.drop_table("second_approvals")
    op.drop_column("purchase_orders", "second_by")
