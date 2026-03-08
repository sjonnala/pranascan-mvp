"""Initial schema — consent_records, scan_sessions, scan_results, audit_logs.

Revision ID: 001
Revises:
Create Date: 2026-03-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("consent_version", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(256), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deletion_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])

    op.create_table(
        "scan_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="initiated"),
        sa.Column("device_model", sa.String(128), nullable=True),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scan_sessions_user_id", "scan_sessions", ["user_id"])

    op.create_table(
        "scan_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False, unique=True, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("hr_bpm", sa.Float, nullable=True),
        sa.Column("hrv_ms", sa.Float, nullable=True),
        sa.Column("respiratory_rate", sa.Float, nullable=True),
        sa.Column("voice_jitter_pct", sa.Float, nullable=True),
        sa.Column("voice_shimmer_pct", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("lighting_score", sa.Float, nullable=True),
        sa.Column("motion_score", sa.Float, nullable=True),
        sa.Column("face_confidence", sa.Float, nullable=True),
        sa.Column("audio_snr_db", sa.Float, nullable=True),
        sa.Column("flags", sa.JSON, nullable=True),
        sa.Column("trend_alert", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scan_results_user_id", "scan_results", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("action", sa.String(128), nullable=False, index=True),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("http_method", sa.String(8), nullable=False),
        sa.Column("http_path", sa.String(512), nullable=False),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("scan_results")
    op.drop_table("scan_sessions")
    op.drop_table("consent_records")
