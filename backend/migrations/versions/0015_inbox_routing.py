"""Inbound mail routing: which request and supplier a mail belongs to

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inbox_emails", sa.Column("route", sa.String(16)))
    op.add_column(
        "inbox_emails", sa.Column("route_request_id", sa.Integer(), sa.ForeignKey("customer_requests.id"))
    )
    op.add_column("inbox_emails", sa.Column("route_supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id")))
    op.add_column("inbox_emails", sa.Column("route_reason", sa.String(300)))
    op.add_column("inbox_emails", sa.Column("routed_by", sa.String(128)))


def downgrade() -> None:
    for col in ("routed_by", "route_reason", "route_supplier_id", "route_request_id", "route"):
        op.drop_column("inbox_emails", col)
