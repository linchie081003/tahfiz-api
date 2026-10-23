"""sesi harian + rentang ayat pada penilaian

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = insp.get_table_names()
    if "evaluations" in tables:
        have = {c["name"] for c in insp.get_columns("evaluations")}
        if "ayah_start" not in have:
            op.add_column("evaluations", sa.Column("ayah_start", sa.Integer(), nullable=True))
        if "ayah_end" not in have:
            op.add_column("evaluations", sa.Column("ayah_end", sa.Integer(), nullable=True))
    if "daily_sessions" not in tables:
        op.create_table(
            "daily_sessions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.id"), nullable=False, index=True),
            sa.Column("day", sa.Date(), nullable=False, index=True),
            sa.Column("kind", sa.String(8), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="available"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("activity_type", sa.String(24), nullable=True),
            sa.Column("activity_id", sa.Uuid(), nullable=True),
            sa.Column("ayah_done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("decided_by", sa.Uuid(), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("member_id", "day", "kind", name="uq_daily_session_member_day_kind"),
        )


def downgrade() -> None:
    op.drop_table("daily_sessions")
    op.drop_column("evaluations", "ayah_end")
    op.drop_column("evaluations", "ayah_start")
