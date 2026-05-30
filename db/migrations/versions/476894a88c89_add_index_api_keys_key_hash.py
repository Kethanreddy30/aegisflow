"""add audit_log index and tenant_providers unique constraint

Revision ID: 476894a88c89
Revises: 8b77726a9977
Create Date: 2026-05-30 11:24:27.892775
"""
from typing import Sequence, Union
from alembic import op

revision: str = '476894a88c89'
down_revision: Union[str, Sequence[str], None] = '8b77726a9977'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for efficient per-tenant audit log queries
    op.create_index(
        "ix_audit_log_tenant_created",
        "audit_log",
        ["tenant_id", "created_at"],
    )
    # Prevent same key_ref registered twice for same tenant
    op.create_unique_constraint(
        "uq_tenant_provider_key_ref",
        "tenant_providers",
        ["tenant_id", "key_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_tenant_created", table_name="audit_log")
    op.drop_constraint("uq_tenant_provider_key_ref", "tenant_providers")
