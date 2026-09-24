"""telemetry: think_ms, started_at, client_info, rules

Revision ID: 0002_telemetry
Revises: 8d1a326f879a
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_telemetry"
down_revision = "8d1a326f879a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("game_logs", sa.Column("think_ms", postgresql.ARRAY(sa.Integer()), nullable=True))
    op.add_column("game_logs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_logs", sa.Column("client_info", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("game_logs", sa.Column("rules", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("game_logs", "rules")
    op.drop_column("game_logs", "client_info")
    op.drop_column("game_logs", "started_at")
    op.drop_column("game_logs", "think_ms")
