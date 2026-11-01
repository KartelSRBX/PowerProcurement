"""Supplier bank accounts and the proposals that change them

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_bank_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False, unique=True),
        sa.Column("account_encrypted", sa.Text(), nullable=False),
        sa.Column("account_hash", sa.String(64), nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("holder", sa.String(200), nullable=False),
        sa.Column("bank_name", sa.String(200)),
        sa.Column("swift", sa.String(11)),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_by", sa.String(128), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "supplier_bank_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("account_encrypted", sa.Text(), nullable=False),
        sa.Column("account_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("holder", sa.String(200), nullable=False),
        sa.Column("bank_name", sa.String(200)),
        sa.Column("swift", sa.String(11)),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("proposed_by", sa.String(128), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("callback_by", sa.String(128), nullable=False),
        sa.Column("callback_person", sa.String(200), nullable=False),
        sa.Column("callback_source", sa.String(24), nullable=False),
        sa.Column("callback_on", sa.Date(), nullable=False),
        sa.Column("callback_note", sa.String(300), nullable=False, server_default=""),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(128)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_comment", sa.String(300)),
    )


def downgrade() -> None:
    op.drop_table("supplier_bank_changes")
    op.drop_table("supplier_bank_accounts")
