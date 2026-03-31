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


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name)) or any(
        constraint.get("name") == index_name for constraint in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    if not _has_table("beta_invites"):
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
    if not _has_index("beta_invites", "ix_beta_invites_code"):
        op.create_index("ix_beta_invites_code", "beta_invites", ["code"], unique=True)

    if not _has_table("beta_enrollments"):
        op.create_table(
            "beta_enrollments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("invite_id", sa.String(36), nullable=False),
            sa.Column("invite_code", sa.String(64), nullable=False),
            sa.Column("cohort_name", sa.String(64), nullable=False),
            sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _has_index("beta_enrollments", "ix_beta_enrollments_user_id"):
        op.create_index("ix_beta_enrollments_user_id", "beta_enrollments", ["user_id"], unique=True)
    if not _has_index("beta_enrollments", "ix_beta_enrollments_invite_id"):
        op.create_index("ix_beta_enrollments_invite_id", "beta_enrollments", ["invite_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_beta_enrollments_invite_id", table_name="beta_enrollments")
    op.drop_index("ix_beta_enrollments_user_id", table_name="beta_enrollments")
    op.drop_table("beta_enrollments")
    op.drop_index("ix_beta_invites_code", table_name="beta_invites")
    op.drop_table("beta_invites")
