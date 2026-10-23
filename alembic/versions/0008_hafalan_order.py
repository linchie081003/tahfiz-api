"""urutan hafalan (berurutan/bebas) dan surat fokus

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "member_settings" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("member_settings")}
        if "hafalan_order" not in have:
            op.add_column("member_settings", sa.Column("hafalan_order", sa.String(16), nullable=False, server_default="sequential"))
        if "focus_surah_id" not in have:
            op.add_column("member_settings", sa.Column("focus_surah_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("member_settings", "focus_surah_id")
    op.drop_column("member_settings", "hafalan_order")
