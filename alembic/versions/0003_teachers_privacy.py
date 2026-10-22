"""guru, instansi, izin rekaman, log akses, hapus/unduh, pesan, pindah instansi

Idempoten. Menambah kolom ke families dan submissions, lalu membuat tabel baru.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

from app.database import Base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "institutions", "teachers", "teacher_documents", "teacher_links", "recording_access_logs",
    "deletion_requests", "teacher_messages", "transfer_requests",
]
COLUMNS = {
    "families": [
        ("recording_consent_at", sa.DateTime(timezone=True)),
        ("recording_consent_by", sa.Uuid()),
        ("institution_id", sa.Uuid()),
    ],
    "submissions": [("recording_deleted_at", sa.DateTime(timezone=True))],
}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table, cols in COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, typ in cols:
            if name not in have:
                op.add_column(table, sa.Column(name, typ, nullable=True))
    tables = [t for t in Base.metadata.sorted_tables if t.name in NEW_TABLES]
    Base.metadata.create_all(bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(NEW_TABLES):
        op.drop_table(name)
    for table, cols in COLUMNS.items():
        for name, _ in cols:
            op.drop_column(table, name)
