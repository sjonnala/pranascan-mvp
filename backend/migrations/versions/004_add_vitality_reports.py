"""Add vitality_reports table.

Revision ID: 004
Revises: 003
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name)) or any(
        constraint.get("name") == index_name for constraint in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    if not _has_table("vitality_reports"):
        op.create_table(
            "vitality_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("scan_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("alert_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("avg_hr_bpm", sa.Float, nullable=True),
            sa.Column("avg_hrv_ms", sa.Float, nullable=True),
            sa.Column("avg_respiratory_rate", sa.Float, nullable=True),
            sa.Column("avg_voice_jitter_pct", sa.Float, nullable=True),
            sa.Column("avg_voice_shimmer_pct", sa.Float, nullable=True),
            sa.Column("delta_hr_bpm", sa.Float, nullable=True),
            sa.Column("delta_hrv_ms", sa.Float, nullable=True),
            sa.Column("latest_vascular_age_estimate", sa.Float, nullable=True),
            sa.Column("latest_vascular_age_confidence", sa.Float, nullable=True),
            sa.Column("latest_anemia_label", sa.String(32), nullable=True),
            sa.Column("latest_anemia_confidence", sa.Float, nullable=True),
            sa.Column("summary_text", sa.Text, nullable=False, server_default=""),
            sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _has_index("vitality_reports", "ix_vitality_reports_user_id"):
        op.create_index("ix_vitality_reports_user_id", "vitality_reports", ["user_id"])


def downgrade() -> None:
    op.drop_table("vitality_reports")
