"""Add users and otp_requests tables for phone+OTP auth.

Revision ID: 007
Revises: 006
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
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
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("phone_e164", sa.String(20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _has_index("users", "ix_users_phone_e164"):
        op.create_index("ix_users_phone_e164", "users", ["phone_e164"], unique=True)

    if not _has_table("otp_requests"):
        op.create_table(
            "otp_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("phone_e164", sa.String(20), nullable=False),
            sa.Column("otp_hash", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _has_index("otp_requests", "ix_otp_requests_phone_e164"):
        op.create_index("ix_otp_requests_phone_e164", "otp_requests", ["phone_e164"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_otp_requests_phone_e164", table_name="otp_requests")
    op.drop_table("otp_requests")
    op.drop_index("ix_users_phone_e164", table_name="users")
    op.drop_table("users")
