import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models import (
    ApiKey, Tenant, TenantPolicy, TenantProvider,
    TenantConfigSchema, ProviderKeySchema, FailoverPolicySchema,
)
from db.session import get_db

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_MIN_KEY_LENGTH = 10
_MAX_KEY_LENGTH = 256


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, hashed_key). Store only the hash."""
    raw = f"af_{secrets.token_urlsafe(32)}"
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _validate_key_format(api_key: str) -> bool:
    """Basic sanity check before hitting the database."""
    return _MIN_KEY_LENGTH <= len(api_key) <= _MAX_KEY_LENGTH


async def _update_last_used(key_hash: str, db: AsyncSession) -> None:
    """Background task — non-blocking last_used_at update."""
    try:
        async with db as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.key_hash == key_hash)
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()
    except Exception:
        pass  # Non-critical — never crash auth over a timestamp update


async def get_tenant_from_key(
    api_key: Optional[str] = Depends(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> TenantConfigSchema:

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if not _validate_key_format(api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    key_hash = hash_api_key(api_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.status == "active",
        )
    )
    api_key_row = result.scalar_one_or_none()

    if not api_key_row:
        raise HTTPException(status_code=403, detail="Invalid or inactive API key")

    # Fire and forget — don't block the request on a timestamp update
    import asyncio
    from db.session import AsyncSessionFactory
    asyncio.create_task(
        _update_last_used(key_hash, AsyncSessionFactory())
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
            fallback_model=policy.fallback_model if policy else None,
            budget_usd_monthly=(
                float(policy.budget_usd_monthly)
                if policy and policy.budget_usd_monthly else None
            ),
        ),
        masking_enabled=policy.masking_enabled if policy else True,
        allowed_models=policy.allowed_models or [] if policy else [],
    )
