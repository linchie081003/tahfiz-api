"""rentang hafalan, penilaian append-only, penugasan penilai

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _uuid():
    return sa.Uuid()


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "memorized_ranges" not in have:
        op.create_table(
            "memorized_ranges",
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("member_id", _uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("surah_id", sa.Integer(), sa.ForeignKey("surahs.id"), nullable=False, index=True),
            sa.Column("ayah_start", sa.Integer(), nullable=False),
            sa.Column("ayah_end", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="passed"),
            sa.Column("submission_id", _uuid(), sa.ForeignKey("submissions.id"), nullable=True),
            sa.Column("source", sa.String(16), nullable=False, server_default="evaluation"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "evaluations" not in have:
        op.create_table(
            "evaluations",
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("submission_id", _uuid(), sa.ForeignKey("submissions.id"), nullable=False, index=True),
            sa.Column("member_id", _uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("evaluator_id", _uuid(), nullable=True),
            sa.Column("evaluator_role", sa.String(16), nullable=False, server_default="parent"),
            sa.Column("result", sa.String(16), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("rubric_scores", sa.JSON(), nullable=True),
            sa.Column("corrects_id", _uuid(), sa.ForeignKey("evaluations.id"), nullable=True),
            sa.Column("source", sa.String(16), nullable=False, server_default="live"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "evaluator_assignments" not in have:
        op.create_table(
            "evaluator_assignments",
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("member_id", _uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("evaluator_id", _uuid(), nullable=True),
            sa.Column("evaluator_role", sa.String(16), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("changed_by", _uuid(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("evaluator_assignments")
    op.drop_table("evaluations")
    op.drop_table("memorized_ranges")
