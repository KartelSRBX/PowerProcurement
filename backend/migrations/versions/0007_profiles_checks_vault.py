"""supplier profiles, discounts, checks and the access vault

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("brands", "product_types"):
        op.add_column("suppliers", sa.Column(name, sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("suppliers", sa.Column("brand_tiers", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("suppliers", sa.Column("stock_delivery_days", sa.Integer(), nullable=True))
    op.add_column("suppliers", sa.Column("payment_type", sa.String(length=32), nullable=True))
    op.add_column("suppliers", sa.Column("contract_note", sa.String(length=300), nullable=True))
    op.add_column(
        "suppliers", sa.Column("has_credit_line", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("suppliers", sa.Column("credit_line_note", sa.String(length=300), nullable=True))
    op.add_column("suppliers", sa.Column("rebates", sa.String(length=300), nullable=True))
    op.add_column("suppliers", sa.Column("partner_status", sa.String(length=16), nullable=True))
    op.add_column("suppliers", sa.Column("website", sa.String(length=300), nullable=True))

    op.create_table(
        "supplier_discounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "supplier_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("checked_by", sa.String(length=128), nullable=False),
        sa.Column("contact_details", sa.String(length=300), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "vault_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("site_url", sa.String(length=300), nullable=True),
        sa.Column("login_encrypted", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("comments", sa.String(length=500), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "vault_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decision_comment", sa.String(length=300), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["vault_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "vault_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=24), nullable=False),
        sa.Column("person", sa.String(length=128), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=300), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    for table in ("vault_log", "vault_requests", "vault_entries", "supplier_checks", "supplier_discounts"):
        op.drop_table(table)
    for col in (
        "website",
        "partner_status",
        "rebates",
        "credit_line_note",
        "has_credit_line",
        "contract_note",
        "payment_type",
        "stock_delivery_days",
        "brand_tiers",
        "product_types",
        "brands",
    ):
        op.drop_column("suppliers", col)
