import re
import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from control_plane.models import (
    Tenant, TenantProvider, TenantPolicy, ApiKey,
    TenantCreateRequest, TenantCreateResponse,
    ProviderRegisterRequest, PolicyUpdateRequest,
)
from control_plane.auth import generate_api_key
from control_plane.audit import write as audit_write, AuditEvent

SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$')


def validate_slug(slug: str) -> None:
    """
    Slug rules:
    - 3 to 50 characters
    - lowercase letters, digits, hyphens only
    - cannot start or end with a hyphen
    """
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(
            status_code=422,
            detail=(
                "Slug must be 3-50 characters, "
                "lowercase letters/digits/hyphens only, "
                "cannot start or end with a hyphen."
            )
        )


async def create_tenant(
    request: TenantCreateRequest,
    db: AsyncSession,
) -> TenantCreateResponse:

    validate_slug(request.slug)

    # Check slug uniqueness before insert
    existing = await db.execute(
        select(Tenant).where(Tenant.slug == request.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Slug '{request.slug}' already taken")

    try:
        tenant = Tenant(
            name=request.name,
            slug=request.slug,
            status="active",
        )
        db.add(tenant)
        await db.flush()  # get tenant_id, stay in transaction

        policy = TenantPolicy(
            tenant_id=tenant.tenant_id,
            masking_enabled=request.masking_enabled,
        )
        db.add(policy)
        await db.flush()

        raw_key, key_hash = generate_api_key()
        api_key_row = ApiKey(
            key_hash=key_hash,
            tenant_id=tenant.tenant_id,
            label="default",
            status="active",
        )
        db.add(api_key_row)
        await db.flush()

        # Audit — resilient, won't crash if it fails
        await audit_write(
            tenant_id=tenant.tenant_id,
            event_type=AuditEvent.TENANT_CREATED,
            payload={"name": request.name, "slug": request.slug},
            db=db,
        )

        # Single commit happens in get_db() after this returns
        tenant_id = tenant.tenant_id
        slug = tenant.slug

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tenant with this slug already exists")

    return TenantCreateResponse(
        tenant_id=tenant_id,
        slug=slug,
        api_key=raw_key,
    )


async def register_provider(
    tenant_id: uuid.UUID,
    request: ProviderRegisterRequest,
    db: AsyncSession,
) -> dict:

    # Check tenant exists
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check for duplicate key_ref on same tenant
    existing = await db.execute(
        select(TenantProvider).where(
            TenantProvider.tenant_id == tenant_id,
            TenantProvider.key_ref == request.key_ref,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"key_ref '{request.key_ref}' already registered for this tenant"
        )

    # Warn if priority collision exists
    priority_check = await db.execute(
        select(TenantProvider).where(
            TenantProvider.tenant_id == tenant_id,
            TenantProvider.priority == request.priority,
        )
    )
    if priority_check.scalar_one_or_none():
        raise HTTPException(
            status_code=422,
            detail=f"Priority {request.priority} already assigned to another provider. Use a different priority."
        )

    provider = TenantProvider(
        tenant_id=tenant_id,
        provider=request.provider,
        key_ref=request.key_ref,
        priority=request.priority,
        rpm_limit=request.rpm_limit,
        status="healthy",
    )
    db.add(provider)
    await db.flush()

    await audit_write(
        tenant_id=tenant_id,
        event_type=AuditEvent.PROVIDER_REGISTERED,
        payload={"provider": request.provider, "priority": request.priority},
        db=db,
    )

    return {"status": "registered", "provider": request.provider}


async def update_policy(
    tenant_id: uuid.UUID,
    request: PolicyUpdateRequest,
    db: AsyncSession,
) -> dict:

    policy = await db.get(TenantPolicy, tenant_id)
    if not policy:
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

    await db.flush()

    await audit_write(
        tenant_id=tenant_id,
        event_type=AuditEvent.POLICY_UPDATED,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )

    return {"status": "updated"}
