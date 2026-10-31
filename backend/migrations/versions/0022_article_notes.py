"""Article records (brand, end of life), links between articles, authorized brands on a supplier

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("authorized_brands", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table(
        "article_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(200), nullable=False, unique=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(100)),
        sa.Column("eol", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("eol_since", sa.Date()),
        sa.Column("eol_note", sa.String(300), nullable=False, server_default=""),
        sa.Column("set_by", sa.String(128), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "article_alternates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("alternate_key", sa.String(200), nullable=False),
        sa.Column("alternate_label", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("set_by", sa.String(128), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("key", "alternate_key"),
    )


def downgrade() -> None:
    op.drop_table("article_alternates")
    op.drop_table("article_records")
    op.drop_column("suppliers", "authorized_brands")
