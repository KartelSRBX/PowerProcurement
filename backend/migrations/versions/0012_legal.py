"""Legal module: norm base, Incoterms, playbook rules, contracts with clauses and findings

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_sources",
        sa.Column("key", sa.String(48), primary_key=True),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("short", sa.String(80), nullable=False),
        sa.Column("ref", sa.String(80)),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("topics", sa.JSON, nullable=False),
        sa.Column("fetch", sa.String(12), nullable=False),
        sa.Column("source_url", sa.String(500)),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True)),
        sa.Column("loaded_by", sa.String(128)),
        sa.Column("text_hash", sa.String(64)),
        sa.Column("provision_count", sa.Integer, nullable=False),
    )
    op.create_table(
        "legal_provisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_key", sa.String(48), sa.ForeignKey("legal_sources.key"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("number", sa.String(24), nullable=False),
        sa.Column("heading", sa.String(300), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.UniqueConstraint("source_key", "number", name="uq_legal_provision_number"),
    )
    op.create_index("ix_legal_provisions_source_key", "legal_provisions", ["source_key"])
    op.create_table(
        "legal_incoterms",
        sa.Column("code", sa.String(4), primary_key=True),
        sa.Column("version", sa.String(8), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )
    op.create_table(
        "legal_rules",
        sa.Column("key", sa.String(48), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("clause_type", sa.String(32), nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("params", sa.JSON, nullable=False),
        sa.Column("risk", sa.Text, nullable=False),
        sa.Column("suggest", sa.Text, nullable=False),
        sa.Column("citations", sa.JSON, nullable=False),
        sa.Column("draft", sa.Boolean, nullable=False),
        sa.Column("updated_by", sa.String(128)),
    )
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("counterparty", sa.String(300), nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("customer_requests.id")),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("ai_allowed", sa.Boolean, nullable=False),
        sa.Column("ai_model", sa.String(64)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("analysed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("expires_on", sa.Date),
    )
    op.create_index("ix_contracts_request_id", "contracts", ["request_id"])
    op.create_table(
        "contract_clauses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contract_id", sa.Integer, sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("heading", sa.String(200), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("clause_type", sa.String(32), nullable=False),
        sa.Column("types", sa.JSON, nullable=False),
        sa.Column("facts", sa.JSON, nullable=False),
    )
    op.create_index("ix_contract_clauses_contract_id", "contract_clauses", ["contract_id"])
    op.create_table(
        "contract_findings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contract_id", sa.Integer, sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("clause_id", sa.Integer, sa.ForeignKey("contract_clauses.id")),
        sa.Column("rule_key", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("risk", sa.Text, nullable=False),
        sa.Column("suggest", sa.Text, nullable=False),
        sa.Column("citations", sa.JSON, nullable=False),
        sa.Column("by", sa.String(8), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("decided_by", sa.String(128)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text, nullable=False),
    )
    op.create_index("ix_contract_findings_contract_id", "contract_findings", ["contract_id"])


def downgrade() -> None:
    for t in (
        "contract_findings",
        "contract_clauses",
        "contracts",
        "legal_rules",
        "legal_incoterms",
        "legal_provisions",
        "legal_sources",
    ):
        op.drop_table(t)
