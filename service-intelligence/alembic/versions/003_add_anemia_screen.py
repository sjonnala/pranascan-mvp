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


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("scan_results", "hb_proxy_score"):
        op.add_column("scan_results", sa.Column("hb_proxy_score", sa.Float, nullable=True))
    if not _has_column("scan_results", "anemia_wellness_label"):
        op.add_column("scan_results", sa.Column("anemia_wellness_label", sa.String(32), nullable=True))
    if not _has_column("scan_results", "anemia_confidence"):
        op.add_column("scan_results", sa.Column("anemia_confidence", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("scan_results", "anemia_confidence")
    op.drop_column("scan_results", "anemia_wellness_label")
    op.drop_column("scan_results", "hb_proxy_score")
