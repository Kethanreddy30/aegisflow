import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models import (
    Tenant, TenantProvider, TenantPolicy, ApiKey,
    TenantCreateRequest, TenantCreateResponse,
    ProviderRegisterRequest, PolicyUpdateRequest,
)
from control_plane.auth import generate_api_key


async def create_tenant(
    request: TenantCreateRequest,
    db: AsyncSession,
) -> TenantCreateResponse:

    # Check slug is unique
    existing = await db.execute(
        select(Tenant).where(Tenant.slug == request.slug)
    )
    if existing.scalar_one_or_none():
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=f"Slug '{request.slug}' already taken")

    # Create tenant
    tenant = Tenant(
        name=request.name,
        slug=request.slug,
        status="active",
    )
    db.add(tenant)
    await db.flush()  # get tenant_id before policy insert

    # Create default policy
    policy = TenantPolicy(
        tenant_id=tenant.tenant_id,
        masking_enabled=request.masking_enabled,
    )
    db.add(policy)

    # Generate API key — return raw once, store only hash
    raw_key, key_hash = generate_api_key()
    api_key = ApiKey(
        key_hash=key_hash,
        tenant_id=tenant.tenant_id,
        label="default",
        status="active",
    )
    db.add(api_key)
    await db.commit()

    return TenantCreateResponse(
        tenant_id=tenant.tenant_id,
        slug=tenant.slug,
        api_key=raw_key,
    )


async def register_provider(
    tenant_id: uuid.UUID,
    request: ProviderRegisterRequest,
    db: AsyncSession,
) -> dict:

    provider = TenantProvider(
        tenant_id=tenant_id,
        provider=request.provider,
        key_ref=request.key_ref,
        priority=request.priority,
        rpm_limit=request.rpm_limit,
        status="healthy",
    )
    db.add(provider)
    await db.commit()

    return {"status": "registered", "provider": request.provider}


async def update_policy(
    tenant_id: uuid.UUID,
    request: PolicyUpdateRequest,
    db: AsyncSession,
) -> dict:

    policy = await db.get(TenantPolicy, tenant_id)
    if not policy:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tenant policy not found")

    if request.auto_failover is not None:
        policy.auto_failover = request.auto_failover
    if request.notify_admin is not None:
        policy.notify_admin = request.notify_admin
    if request.fallback_to_local is not None:
        policy.fallback_to_local = request.fallback_to_local
    if request.budget_usd_monthly is not None:
        policy.budget_usd_monthly = request.budget_usd_monthly
    if request.allowed_models is not None:
        policy.allowed_models = request.allowed_models

    await db.commit()
    return {"status": "updated"}
