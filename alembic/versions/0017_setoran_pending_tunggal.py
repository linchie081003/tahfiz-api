"""satu setoran pending aktif per rentang ziyadah + penanda superseded

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

WHERE = "context = 'ziyadah' AND status IN ('pending_ai', 'pending_eval')"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "submissions" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("submissions")}
    if "superseded_by_id" not in have:
        op.add_column("submissions", sa.Column("superseded_by_id", sa.Uuid(), sa.ForeignKey("submissions.id"), nullable=True))
    if "superseded_at" not in have:
        op.add_column("submissions", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    if "uq_submissions_pending_range" in {i["name"] for i in insp.get_indexes("submissions")}:
        return
    # Data lama: bila satu rentang punya beberapa setoran pending, yang terbaru dipertahankan, sisanya superseded.
    bind.execute(sa.text("""
        UPDATE submissions s SET status = 'superseded', superseded_at = now(),
               superseded_by_id = (SELECT n.id FROM submissions n
                                   WHERE n.member_id = s.member_id AND n.surah_id = s.surah_id
                                     AND n.ayah_start = s.ayah_start AND n.ayah_end IS NOT DISTINCT FROM s.ayah_end
                                     AND n.context = 'ziyadah' AND n.status IN ('pending_ai','pending_eval')
                                   ORDER BY n.created_at DESC LIMIT 1)
        WHERE s.context = 'ziyadah' AND s.status IN ('pending_ai', 'pending_eval')
          AND EXISTS (SELECT 1 FROM submissions n WHERE n.member_id = s.member_id AND n.surah_id = s.surah_id
                      AND n.ayah_start = s.ayah_start AND n.ayah_end IS NOT DISTINCT FROM s.ayah_end
                      AND n.context = 'ziyadah' AND n.status IN ('pending_ai','pending_eval') AND n.created_at > s.created_at)
    """)) if bind.dialect.name == "postgresql" else None
    op.create_index(
        "uq_submissions_pending_range", "submissions", ["member_id", "surah_id", "ayah_start", "ayah_end"],
        unique=True, postgresql_where=sa.text(WHERE), sqlite_where=sa.text(WHERE),
    )


def downgrade() -> None:
    op.drop_index("uq_submissions_pending_range", table_name="submissions")
    op.drop_column("submissions", "superseded_at")
    op.drop_column("submissions", "superseded_by_id")
