"""baseline: tabel yang sudah ada sebelum konsep baru

Aman dijalankan di database yang sudah dibuat oleh create_all (membuat hanya yang belum ada).

Revision ID: 0001
Revises:
"""
from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NEW_TABLES = {"family_invites", "member_settings", "tahsin_point_progress"}


def upgrade() -> None:
    bind = op.get_bind()
    tables = [t for t in Base.metadata.sorted_tables if t.name not in NEW_TABLES]
    Base.metadata.create_all(bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    pass  # baseline tidak dibatalkan
