"""Add vascular_age columns to scan_results.

Revision ID: 002
Revises: 001
Create Date: 2026-03-09
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_results", sa.Column("vascular_age_estimate", sa.Float, nullable=True))
    op.add_column("scan_results", sa.Column("vascular_age_confidence", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("scan_results", "vascular_age_estimate")
    op.drop_column("scan_results", "vascular_age_confidence")
