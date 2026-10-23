"""koreksi penilaian dan saklar kewenangan orang tua

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "family_settings" in tables:
        have = {c["name"] for c in insp.get_columns("family_settings")}
        if "parent_can_evaluate" not in have:
            op.add_column("family_settings", sa.Column("parent_can_evaluate", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "evaluations" in tables:
        have = {c["name"] for c in insp.get_columns("evaluations")}
        if "correction_reason" not in have:
            op.add_column("evaluations", sa.Column("correction_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluations", "correction_reason")
    op.drop_column("family_settings", "parent_can_evaluate")
