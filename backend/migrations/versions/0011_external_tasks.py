"""Tasks in an outside task system (Bitrix24, Excel) for each request, and their change history

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("customer_requests.id"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("parent_key", sa.String(64)),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(64)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("role", sa.String(64)),
        sa.Column("creator_id", sa.String(64)),
        sa.Column("responsible_id", sa.String(64)),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("raw_status", sa.String(64)),
        sa.Column("stage_id", sa.String(64)),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("remote", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("request_id", "key", name="uq_external_tasks_request_key"),
    )
    op.create_table(
        "external_task_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("external_tasks.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("old", sa.String(300)),
        sa.Column("new", sa.String(300)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("external_task_events")
    op.drop_table("external_tasks")
