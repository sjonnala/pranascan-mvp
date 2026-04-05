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


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("scan_results", "vascular_age_estimate"):
        op.add_column("scan_results", sa.Column("vascular_age_estimate", sa.Float, nullable=True))
    if not _has_column("scan_results", "vascular_age_confidence"):
        op.add_column("scan_results", sa.Column("vascular_age_confidence", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("scan_results", "vascular_age_estimate")
    op.drop_column("scan_results", "vascular_age_confidence")
