"""add deletion_request table

Revision ID: 20240405_add_deletion_request_table
Revises: <previous_revision_id>
Create Date: 2024-04-05 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deletion_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('purged_at', sa.DateTime(), nullable=True),
        sa.Column('failure_reason', sa.String(), nullable=True),
    )
    op.create_index(op.f('ix_deletion_requests_user_id'), 'deletion_requests', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_deletion_requests_user_id'), table_name='deletion_requests')
    op.drop_table('deletion_requests')
