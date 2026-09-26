"""reports on opponents in H2H matches; hidden names

Revision ID: 0003_reports
Revises: 0002_telemetry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_reports"
down_revision = "0002_telemetry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # no FK: during a match its h2h_matches row does not exist yet (written at the end)
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reporter", postgresql.UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("reported", postgresql.UUID(as_uuid=True), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("reported_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("match_id", "reporter", name="uq_report_match_reporter"),
        sa.CheckConstraint("reason IN ('name','impersonation','cheating','stalling','bug')", name="ck_report_reason"),
    )
    op.create_index("ix_reports_reported_reason", "reports", ["reported", "reason"])
    op.add_column("players", sa.Column("name_hidden_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("players", "name_hidden_at")
    op.drop_index("ix_reports_reported_reason", table_name="reports")
    op.drop_table("reports")
