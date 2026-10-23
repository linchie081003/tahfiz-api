"""bukti aktivitas sesi harian (append-only)

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "daily_session_activities" in insp.get_table_names():
        return
    op.create_table(
        "daily_session_activities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("daily_sessions.id"), nullable=False, index=True),
        sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("activity_type", sa.String(24), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=True),
        sa.Column("ayah", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("daily_session_activities")
