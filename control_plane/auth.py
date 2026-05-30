import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models import ApiKey, Tenant, TenantPolicy, TenantProvider
from control_plane.models import TenantConfigSchema, ProviderKeySchema, FailoverPolicySchema
from db.session import get_db

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, hashed_key). Store only the hash."""
    raw = f"af_{secrets.token_urlsafe(32)}"
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_tenant_from_key(
    api_key: Optional[str] = Depends(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> TenantConfigSchema:

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = hash_api_key(api_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.status == "active"
        )
    )
    api_key_row = result.scalar_one_or_none()

    if not api_key_row:
        raise HTTPException(status_code=403, detail="Invalid or inactive API key")

    # Update last_used_at without blocking
    await db.execute(
        update(ApiKey)
        .where(ApiKey.key_hash == key_hash)
        .values(last_used_at=datetime.now(timezone.utc))
    )

    return await load_tenant_config(api_key_row.tenant_id, db)


async def load_tenant_config(tenant_id, db: AsyncSession) -> TenantConfigSchema:

    tenant = await db.get(Tenant, tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=403, detail="Tenant inactive or not found")

    providers_result = await db.execute(
        select(TenantProvider).where(TenantProvider.tenant_id == tenant_id)
    )
    providers = providers_result.scalars().all()

    policy = await db.get(TenantPolicy, tenant_id)

    return TenantConfigSchema(
        tenant_id=tenant.tenant_id,
        slug=tenant.slug,
        providers=[
            ProviderKeySchema(
                key_id=str(p.id),
                provider=p.provider,
                key_ref=p.key_ref,
                priority=p.priority,
                rpm_limit=p.rpm_limit,
                status=p.status,
            )
            for p in sorted(providers, key=lambda x: x.priority)
        ],
        policy=FailoverPolicySchema(
            automatic=policy.auto_failover if policy else True,
            notify_admin=policy.notify_admin if policy else True,
            fallback_to_local=policy.fallback_to_local if policy else True,
            budget_usd_monthly=float(policy.budget_usd_monthly) if policy and policy.budget_usd_monthly else None,
        ),
        masking_enabled=policy.masking_enabled if policy else True,
        allowed_models=policy.allowed_models if policy else [],
    )
