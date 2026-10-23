"""antrean pra-cek STT (stt_jobs)

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "stt_jobs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "stt_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("submission_id", name="uq_stt_jobs_submission"),
    )
    op.create_index("ix_stt_jobs_status", "stt_jobs", ["status"])
    op.create_index("ix_stt_jobs_next_attempt_at", "stt_jobs", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_table("stt_jobs")
