"""Offer terms: validity date, Incoterms rule and place, payment days

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("valid_until", sa.Date()))
    op.add_column("offers", sa.Column("incoterm", sa.String(3)))
    op.add_column("offers", sa.Column("incoterm_place", sa.String(120)))
    op.add_column("offers", sa.Column("payment_days", sa.Integer()))


def downgrade() -> None:
    for col in ("payment_days", "incoterm_place", "incoterm", "valid_until"):
        op.drop_column("offers", col)
