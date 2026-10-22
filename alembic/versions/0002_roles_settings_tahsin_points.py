"""peran orang tua, undangan, pengaturan per anak, kemajuan 9 Pulau

Idempoten: aman bila sebagian sudah dibuat oleh create_all.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

from app.database import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_TABLES = ["family_invites", "member_settings", "tahsin_point_progress"]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("parent_users")}
    if "family_role" not in cols:
        op.add_column(
            "parent_users",
            sa.Column("family_role", sa.String(16), nullable=False, server_default="owner"),
        )
    tables = [t for t in Base.metadata.sorted_tables if t.name in NEW_TABLES]
    Base.metadata.create_all(bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(NEW_TABLES):
        op.drop_table(name)
    op.drop_column("parent_users", "family_role")
