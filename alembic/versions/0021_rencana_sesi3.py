"""sampel Sesi 3 yang dikeluarkan per hari (daily_sessions.plan)

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("daily_sessions")}
    if "plan" not in cols:
        op.add_column("daily_sessions", sa.Column("plan", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_sessions", "plan")
