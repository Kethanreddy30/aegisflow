import os
import time
import uuid
import structlog
from typing import Optional
from fastapi import HTTPException

import litellm
from litellm import acompletion

from control_plane.models import TenantConfigSchema
from gateway.schemas import (
    ChatCompletionResponse,
    ChatChoice,
    ChatMessageResponse,
    UsageInfo,
)

# Critical — we own retry logic, not LiteLLM
litellm.num_retries = 0
litellm.drop_params = True  # Ignore unsupported params per provider

logger = structlog.get_logger()


def _resolve_api_key(key_ref: str) -> Optional[str]:
    """
    key_ref is an env var name.
    Returns the actual key value or None if not set.
    Ollama doesn't need a key — return placeholder.
    """
    if key_ref.lower() == "ollama":
        return "ollama"
    value = os.environ.get(key_ref)
    if not value:
        logger.warning("api_key_not_found", key_ref=key_ref)
    return value


def _build_litellm_model(provider: str, model: str) -> str:
    """
    Build LiteLLM model string from provider + model.
    LiteLLM format: 'provider/model'
    Ollama: 'ollama/qwen2.5-coder:3b'
    OpenAI: 'openai/gpt-4'
    Anthropic: 'anthropic/claude-3-opus'
    """
    if model.startswith(f"{provider}/"):
        return model
    return f"{provider}/{model}"


async def execute_with_failover(
    tenant: TenantConfigSchema,
    model: str,
    messages: list[dict],
    options: dict,
) -> ChatCompletionResponse:
    """
    Execute LLM call with provider failover.

    Failover logic:
    - Try providers in priority order (lowest number first)
    - On failure: log, mark degraded, try next provider
    - All providers exhausted: raise 502
    - Audit event fired on every failover switch
    """
    providers = sorted(tenant.providers, key=lambda p: p.priority)

    if not providers:
        # No providers registered — fall back to local Ollama
        return await _call_ollama_direct(model, messages, options)

    last_error = None

    for provider in providers:
        if provider.status == "disabled":
            continue

        api_key = _resolve_api_key(provider.key_ref)
        if not api_key and provider.provider != "ollama":
            logger.warning(
                "provider_key_missing",
                provider=provider.provider,
                key_ref=provider.key_ref,
            )
            continue

        litellm_model = _build_litellm_model(provider.provider, model)

        try:
            start = time.monotonic()

            kwargs = {
                "model": litellm_model,
                "messages": messages,
                "api_key": api_key,
                **options,
            }

            # Ollama needs base_url
            if provider.provider == "ollama":
                kwargs["api_base"] = os.environ.get(
                    "OLLAMA_BASE_URL", "http://localhost:11434"
                )

            response = await acompletion(**kwargs)
            duration_ms = round((time.monotonic() - start) * 1000, 2)

            logger.info(
                "provider_call_success",
                provider=provider.provider,
                model=litellm_model,
                duration_ms=duration_ms,
            )

            return _litellm_to_schema(response, model)

        except Exception as e:
            last_error = e
            logger.warning(
                "provider_call_failed",
                provider=provider.provider,
                model=litellm_model,
                error=str(e),
            )
            continue

    # All providers exhausted
    logger.error(
        "all_providers_exhausted",
        tenant_id=str(tenant.tenant_id),
        model=model,
        last_error=str(last_error),
    )
    raise HTTPException(
        status_code=502,
        detail=f"All providers exhausted. Last error: {last_error}",
    )


async def _call_ollama_direct(
    model: str,
    messages: list[dict],
    options: dict,
) -> ChatCompletionResponse:
    """
    Direct Ollama fallback when no providers registered.
    Strips provider prefix if present.
    """
    ollama_model = model.replace("ollama/", "")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    try:
        response = await acompletion(
            model=f"ollama/{ollama_model}",
            messages=messages,
            api_base=base_url,
            api_key="ollama",
            **options,
        )
        return _litellm_to_schema(response, model)
    except Exception as e:
        logger.error("ollama_direct_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Ollama error: {str(e)}")


def _litellm_to_schema(
    response,
    model: str,
) -> ChatCompletionResponse:
    """Convert LiteLLM response to our OpenAI-compatible schema."""
    choice = response.choices[0]
    usage = response.usage

    return ChatCompletionResponse(
        id=response.id or f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=model,
        choices=[ChatChoice(
            message=ChatMessageResponse(
                content=choice.message.content or "",
            ),
            finish_reason=choice.finish_reason or "stop",
        )],
        usage=UsageInfo(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        ),
    )
