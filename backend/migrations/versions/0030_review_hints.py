"""Reviewer hints: the template text of a letter, and when it was decided

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

TABLES = ("rfqs", "customer_quotes", "letters")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("template_body", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "template_body")
        op.drop_column(table, "decided_at")
