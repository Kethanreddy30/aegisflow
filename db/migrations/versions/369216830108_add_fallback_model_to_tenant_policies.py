"""add fallback_model to tenant_policies

Revision ID: 369216830108
Revises: 476894a88c89
Create Date: 2026-06-03 04:05:43.946966
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '369216830108'
down_revision: Union[str, Sequence[str], None] = '476894a88c89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenant_policies',
        sa.Column('fallback_model', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tenant_policies', 'fallback_model')
