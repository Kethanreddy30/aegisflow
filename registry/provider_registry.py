import structlog
from typing import Optional
from control_plane.models import TenantConfigSchema
from gateway.schemas import ModelRoutingResult

logger = structlog.get_logger()


def resolve_model(
    tenant: TenantConfigSchema,
    requested_model: str,
) -> ModelRoutingResult:
    """
    3-tier model routing logic.

    Tier 1: model in allowed_models → route directly
    Tier 2: allowed_models empty → allow all (no restriction)
    Tier 3: model not in allowed_models + list non-empty:
        - fallback_model configured → remap + flag for audit
        - no fallback → raise 403
    """
    from fastapi import HTTPException

    allowed = tenant.allowed_models or []

    # Tier 1 — explicitly allowed
    if requested_model in allowed:
        return ModelRoutingResult(
            resolved_model=requested_model,
            requested_model=requested_model,
            was_remapped=False,
        )

    # Tier 2 — no restrictions set
    if not allowed:
        return ModelRoutingResult(
            resolved_model=requested_model,
            requested_model=requested_model,
            was_remapped=False,
        )

    # Tier 3 — model not allowed, list is non-empty
    fallback = getattr(tenant.policy, "fallback_model", None)

    if fallback:
        logger.warning(
            "model_remapped",
            requested=requested_model,
            served=fallback,
            tenant_id=str(tenant.tenant_id),
        )
        return ModelRoutingResult(
            resolved_model=fallback,
            requested_model=requested_model,
            was_remapped=True,
            remap_reason=f"requested {requested_model} not in allowed_models, remapped to {fallback}",
        )

    # No fallback — hard reject
    raise HTTPException(
        status_code=403,
        detail=f"Model '{requested_model}' is not permitted for this tenant and no fallback is configured.",
    )
