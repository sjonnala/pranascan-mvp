"""Add anemia screening columns to scan_results.

Revision ID: 003
Revises: 002
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_results", sa.Column("hb_proxy_score", sa.Float, nullable=True))
    op.add_column("scan_results", sa.Column("anemia_wellness_label", sa.String(32), nullable=True))
    op.add_column("scan_results", sa.Column("anemia_confidence", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("scan_results", "anemia_confidence")
    op.drop_column("scan_results", "anemia_wellness_label")
    op.drop_column("scan_results", "hb_proxy_score")
