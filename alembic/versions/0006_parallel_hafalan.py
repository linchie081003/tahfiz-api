"""opsi hafalan paralel dengan tahsin

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "member_settings" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("member_settings")}
        if "parallel_hafalan" not in have:
            op.add_column("member_settings", sa.Column("parallel_hafalan", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("member_settings", "parallel_hafalan")
