"""kemajuan Tilawah tersimpan di server

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tilawah_state" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "tilawah_state",
        sa.Column("owner_id", sa.Uuid(), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("tilawah_state")
