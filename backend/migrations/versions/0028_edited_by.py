"""Who last edited the text of an RFQ, a customer quote or a letter

Revision ID: 0028
Revises: 0027
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

TABLES = ("rfqs", "customer_quotes", "letters")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("edited_by", sa.String(128), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "edited_by")
