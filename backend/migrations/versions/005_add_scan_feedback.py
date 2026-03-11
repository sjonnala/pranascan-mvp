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


def upgrade() -> None:
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
    op.create_index("ix_scan_feedback_session_id", "scan_feedback", ["session_id"], unique=True)
    op.create_index("ix_scan_feedback_user_id", "scan_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_feedback_user_id", table_name="scan_feedback")
    op.drop_index("ix_scan_feedback_session_id", table_name="scan_feedback")
    op.drop_table("scan_feedback")
