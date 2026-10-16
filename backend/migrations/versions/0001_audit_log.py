"""create audit_log

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.CheckConstraint("actor in ('system', 'human', 'client')", name="audit_log_actor_ck"),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
