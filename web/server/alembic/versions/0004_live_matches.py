"""live_matches: state of unfinished H2H matches, so they survive a restart

Revision ID: 0004_live_matches
Revises: 0003_reports
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_live_matches"
down_revision = "0003_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "live_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("live_matches")
