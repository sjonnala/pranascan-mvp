"""Add scan_feedback table.

Revision ID: 005
Revises: 004
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
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
    if not _has_table("scan_feedback"):
        op.create_table(
            "scan_feedback",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), nullable=False, unique=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("useful_response", sa.String(16), nullable=False),
            sa.Column("nps_score", sa.Integer, nullable=True),
            sa.Column("comment", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _has_index("scan_feedback", "ix_scan_feedback_session_id"):
        op.create_index("ix_scan_feedback_session_id", "scan_feedback", ["session_id"], unique=True)
    if not _has_index("scan_feedback", "ix_scan_feedback_user_id"):
        op.create_index("ix_scan_feedback_user_id", "scan_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_feedback_user_id", table_name="scan_feedback")
    op.drop_index("ix_scan_feedback_session_id", table_name="scan_feedback")
    op.drop_table("scan_feedback")
