"""tingkat awal bacaan anak (onboarding)

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "member_settings" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("member_settings")}
        if "placement" not in have:
            op.add_column("member_settings", sa.Column("placement", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("member_settings", "placement")
