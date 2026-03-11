"""Add closed beta invite and enrollment tables.

Revision ID: 006
Revises: 005
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("cohort_name", sa.String(64), nullable=False),
        sa.Column("max_redemptions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("redemption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_beta_invites_code", "beta_invites", ["code"], unique=True)

    op.create_table(
        "beta_enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("invite_id", sa.String(36), nullable=False),
        sa.Column("invite_code", sa.String(64), nullable=False),
        sa.Column("cohort_name", sa.String(64), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_beta_enrollments_user_id", "beta_enrollments", ["user_id"], unique=True)
    op.create_index("ix_beta_enrollments_invite_id", "beta_enrollments", ["invite_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_beta_enrollments_invite_id", table_name="beta_enrollments")
    op.drop_index("ix_beta_enrollments_user_id", table_name="beta_enrollments")
    op.drop_table("beta_enrollments")
    op.drop_index("ix_beta_invites_code", table_name="beta_invites")
    op.drop_table("beta_invites")
