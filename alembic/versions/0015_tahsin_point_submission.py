"""nomor Pulau pada setoran latihan Tahsin

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "submissions" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("submissions")}
        if "tahsin_point" not in have:
            op.add_column("submissions", sa.Column("tahsin_point", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "tahsin_point")
