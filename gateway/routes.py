import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models import (
    TenantCreateRequest, TenantCreateResponse,
    ProviderRegisterRequest, PolicyUpdateRequest,
)
from control_plane.registry import create_tenant, register_provider, update_policy
from control_plane.auth import get_tenant_from_key, TenantConfigSchema
from db.session import get_db

tenant_router = APIRouter()


@tenant_router.post("/create", response_model=TenantCreateResponse)
async def create_tenant_route(
    request: TenantCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await create_tenant(request, db)


@tenant_router.post("/{tenant_id}/provider")
async def register_provider_route(
    tenant_id: uuid.UUID,
    request: ProviderRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    return await register_provider(tenant_id, request, db)


@tenant_router.patch("/{tenant_id}/policy")
async def update_policy_route(
    tenant_id: uuid.UUID,
    request: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await update_policy(tenant_id, request, db)


@tenant_router.get("/me")
async def get_me(
    tenant: TenantConfigSchema = Depends(get_tenant_from_key),
):
    return {
        "tenant_id": str(tenant.tenant_id),
        "slug": tenant.slug,
        "masking_enabled": tenant.masking_enabled,
        "providers": len(tenant.providers),
    }
