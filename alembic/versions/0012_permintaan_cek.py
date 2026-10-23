"""permintaan cek dari Sesi 3

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
    if "evaluation_requests" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "evaluation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("submissions.id"), nullable=False, index=True),
        sa.Column("surah_id", sa.Integer(), nullable=False),
        sa.Column("ayah_number", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("assignee_role", sa.String(16), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(8), nullable=False, server_default="open"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_by_role", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("evaluation_requests")
