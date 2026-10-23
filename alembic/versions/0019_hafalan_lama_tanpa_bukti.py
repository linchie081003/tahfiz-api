"""kolom verifikasi rentang + turunkan hasil migrasi tanpa bukti ke unverified

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "memorized_ranges" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("memorized_ranges")}
    for name, col in (
        ("note", sa.Text()),
        ("verified_by", sa.Uuid()),
        ("verified_role", sa.String(16)),
        ("verified_at", sa.DateTime(timezone=True)),
    ):
        if name not in have:
            op.add_column("memorized_ranges", sa.Column(name, col, nullable=True))
    # Hasil migrasi berstatus passed tanpa bukti penilaian lulus -> unverified; jadwal murajaah terbukanya dihentikan.
    cond = """
        r.source = 'migration' AND r.status = 'passed' AND NOT EXISTS (
            SELECT 1 FROM submissions s WHERE s.id = r.submission_id AND s.status = 'passed' AND s.evaluated_at IS NOT NULL)
    """
    bind.execute(sa.text(f"""
        UPDATE murojaah_items m SET completed = true
        WHERE m.completed = false AND m.range_id IN (SELECT r.id FROM memorized_ranges r WHERE {cond})
    """))
    bind.execute(sa.text(f"""
        UPDATE memorized_ranges r SET status = 'unverified',
               note = COALESCE(r.note, 'Hasil migrasi tanpa bukti penilaian lulus; perlu verifikasi manual')
        WHERE {cond}
    """))


def downgrade() -> None:
    for name in ("verified_at", "verified_role", "verified_by", "note"):
        op.drop_column("memorized_ranges", name)
