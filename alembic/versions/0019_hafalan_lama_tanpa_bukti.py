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
    # Progres surat tidak boleh lebih maju dari bukti: turunkan surat lulus / posisi ayat yang bertumpu pada rentang unverified.
    bind.execute(sa.text("""
        UPDATE member_surah_progress p SET
            current_ayah = LEAST(p.current_ayah, u.first_ayah),
            status = CASE WHEN p.status = 'passed' THEN 'in_progress' ELSE p.status END
        FROM (SELECT member_id, surah_id, MIN(ayah_start) AS first_ayah
              FROM memorized_ranges WHERE status = 'unverified' GROUP BY member_id, surah_id) u
        WHERE p.member_id = u.member_id AND p.surah_id = u.surah_id
    """))


def downgrade() -> None:
    for name in ("verified_at", "verified_role", "verified_by", "note"):
        op.drop_column("memorized_ranges", name)
