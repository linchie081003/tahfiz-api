"""percobaan latihan per ayat, tanda sulit, sambung ayat

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _ts(name="created_at"):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now())


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "practice_attempts" not in have:
        op.create_table(
            "practice_attempts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("surah_id", sa.Integer(), sa.ForeignKey("surahs.id"), nullable=False),
            sa.Column("ayah_number", sa.Integer(), nullable=False),
            sa.Column("result", sa.String(8), nullable=False),
            _ts(),
        )
    if "difficult_marks" not in have:
        op.create_table(
            "difficult_marks",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("surah_id", sa.Integer(), sa.ForeignKey("surahs.id"), nullable=False),
            sa.Column("ayah_number", sa.Integer(), nullable=False),
            sa.Column("word_start", sa.Integer(), nullable=True),
            sa.Column("word_end", sa.Integer(), nullable=True),
            sa.Column("word_text", sa.Text(), nullable=True),
            sa.Column("source", sa.String(8), nullable=False, server_default="manual"),
            sa.Column("created_by_role", sa.String(16), nullable=False, server_default="child"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("status", sa.String(8), nullable=False, server_default="active"),
            sa.Column("inactive_reason", sa.String(32), nullable=True),
            sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
            _ts(),
            _ts("updated_at"),
        )
    if "connect_attempts" not in have:
        op.create_table(
            "connect_attempts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False, index=True),
            sa.Column("surah_id", sa.Integer(), sa.ForeignKey("surahs.id"), nullable=False),
            sa.Column("ayah_from", sa.Integer(), nullable=False),
            sa.Column("mode", sa.String(8), nullable=False),
            sa.Column("result", sa.String(8), nullable=False),
            sa.Column("correct", sa.Boolean(), nullable=True),
            sa.Column("rewarded", sa.Boolean(), nullable=False, server_default=sa.false()),
            _ts(),
        )


def downgrade() -> None:
    op.drop_table("connect_attempts")
    op.drop_table("difficult_marks")
    op.drop_table("practice_attempts")
