import uuid

from fastapi import HTTPException

from control_plane.models import (
    TenantConfigSchema,
    FailoverPolicySchema,
)
from registry.provider_registry import resolve_model


def build_tenant(
    allowed_models,
    fallback_model=None,
):
    return TenantConfigSchema(
        tenant_id=uuid.uuid4(),
        slug="test-tenant",
        providers=[],
        policy=FailoverPolicySchema(
            fallback_model=fallback_model,
        ),
        masking_enabled=True,
        allowed_models=allowed_models,
    )


def test_allowed_model_passes_through():
    tenant = build_tenant(
        allowed_models=["gpt-4"],
    )

    result = resolve_model(
        tenant,
        "gpt-4",
    )

    assert result.resolved_model == "gpt-4"
    assert result.requested_model == "gpt-4"
    assert result.was_remapped is False


def test_disallowed_model_remaps_to_fallback():
    tenant = build_tenant(
        allowed_models=["gpt-4"],
        fallback_model="gpt-4o-mini",
    )

    result = resolve_model(
        tenant,
        "claude-3",
    )

    assert result.resolved_model == "gpt-4o-mini"
    assert result.requested_model == "claude-3"
    assert result.was_remapped is True


def test_disallowed_model_without_fallback_rejected():
    tenant = build_tenant(
        allowed_models=["gpt-4"],
    )

    try:
        resolve_model(
            tenant,
            "claude-3",
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
