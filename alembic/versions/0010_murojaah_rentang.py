"""jadwal murajaah per rentang ayat

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "murojaah_items" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("murojaah_items")}
        if "range_id" not in have:
            op.add_column("murojaah_items", sa.Column("range_id", sa.Uuid(), nullable=True))
        if "ayah_start" not in have:
            op.add_column("murojaah_items", sa.Column("ayah_start", sa.Integer(), nullable=True))
        if "ayah_end" not in have:
            op.add_column("murojaah_items", sa.Column("ayah_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("murojaah_items", "ayah_end")
    op.drop_column("murojaah_items", "ayah_start")
    op.drop_column("murojaah_items", "range_id")
