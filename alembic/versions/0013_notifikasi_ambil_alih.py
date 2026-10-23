"""notifikasi dalam aplikasi dan pengambilalihan penilaian manual

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
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "app_notifications" not in have:
        op.create_table(
            "app_notifications",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("recipient_role", sa.String(8), nullable=False, index=True),
            sa.Column("recipient_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("kind", sa.String(24), nullable=False),
            sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("submissions.id"), nullable=False),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("body", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("recipient_role", "recipient_id", "kind", "submission_id"),
        )
    if "evaluation_takeovers" not in have:
        op.create_table(
            "evaluation_takeovers",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("submissions.id"), nullable=False, index=True),
            sa.Column("from_role", sa.String(16), nullable=False),
            sa.Column("from_id", sa.Uuid(), nullable=True),
            sa.Column("to_role", sa.String(16), nullable=False),
            sa.Column("to_id", sa.Uuid(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("evaluation_takeovers")
    op.drop_table("app_notifications")
