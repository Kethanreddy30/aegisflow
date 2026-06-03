import time
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from control_plane.auth import get_tenant_from_key, TenantConfigSchema
from control_plane.audit import write as audit_write, AuditEvent
from db.session import get_db
from gateway.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    ChatMessageResponse,
    UsageInfo,
    GatewayError,
)
from gateway.streaming import make_streaming_response, _make_chunk, _make_done
from registry.provider_registry import resolve_model
from cache.semantic import get_cached_response, set_cached_response
from experts.executor import execute_with_failover

logger = structlog.get_logger()

proxy_router = APIRouter()

OLLAMA_BASE_URL = "http://localhost:11434"


async def get_redis() -> Redis:
    """Redis dependency — single connection per request."""
    from redis.asyncio import from_url
    import os
    redis = from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
    )
    try:
        yield redis
    finally:
        await redis.aclose()


@proxy_router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    tenant: TenantConfigSchema = Depends(get_tenant_from_key),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    structlog.contextvars.bind_contextvars(
        tenant_id=str(tenant.tenant_id),
        requested_model=request.model,
    )

    # ── Step 1: 3-tier model routing ─────────────────────────────────────────
    routing = resolve_model(tenant, request.model)

    if routing.was_remapped:
        await audit_write(
            tenant_id=tenant.tenant_id,
            event_type=AuditEvent.MODEL_REMAPPED,
            payload={
                "requested": routing.requested_model,
                "served": routing.resolved_model,
                "reason": routing.remap_reason,
            },
            db=db,
        )
        structlog.contextvars.bind_contextvars(
            resolved_model=routing.resolved_model,
            remapped=True,
        )

    resolved = routing.resolved_model

    # ── Step 2: Cache check — skip for streaming ──────────────────────────────
    if not request.stream:
        cached = await get_cached_response(
            redis=redis,
            tenant_id=str(tenant.tenant_id),
            model=resolved,
            messages=request.messages,
        )
        if cached:
            await audit_write(
                tenant_id=tenant.tenant_id,
                event_type=AuditEvent.REQUEST_COMPLETED,
                payload={"model": resolved, "cache_hit": True},
                db=db,
            )
            return cached

    # ── Step 3: Build messages + options ─────────────────────────────────────
    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
    ]

    options = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.max_tokens is not None:
        options["max_tokens"] = request.max_tokens
    if request.top_p is not None:
        options["top_p"] = request.top_p

    # ── Step 4: Streaming path ────────────────────────────────────────────────
    if request.stream:
        async def _stream_generator():
            import os
            import json
            import httpx

            ollama_model = resolved.replace("ollama/", "")
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream(
                        "POST",
                        f"{OLLAMA_BASE_URL}/api/chat",
                        json={
                            "model": ollama_model,
                            "messages": messages,
                            "stream": True,
                            "options": options,
                        },
                    ) as resp:
                        if resp.status_code != 200:
                            error_body = await resp.aread()
                            logger.error(
                                "ollama_stream_error",
                                status=resp.status_code,
                                body=error_body.decode(),
                            )
                            yield f"data: {GatewayError.make('Ollama stream failed').model_dump_json()}\n\n"
                            return

                        async for line in resp.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                part = json.loads(line)
                            except Exception:
                                continue

                            content = part.get("message", {}).get("content", "")
                            done = part.get("done", False)

                            if content:
                                yield _make_chunk(chunk_id, resolved, content)

                            if done:
                                yield _make_chunk(
                                    chunk_id, resolved, "", finish_reason="stop"
                                )
                                yield _make_done()
                                await audit_write(
                                    tenant_id=tenant.tenant_id,
                                    event_type=AuditEvent.REQUEST_COMPLETED,
                                    payload={"model": resolved, "stream": True},
                                    db=db,
                                )
                                return

            except Exception as e:
                logger.error("stream_error", error=str(e))
                yield f"data: {GatewayError.make(str(e)).model_dump_json()}\n\n"
                yield _make_done()

        return make_streaming_response(_stream_generator())

    # ── Step 5: Non-streaming — LiteLLM with failover ─────────────────────────
    try:
        response = await execute_with_failover(
            tenant=tenant,
            model=resolved,
            messages=messages,
            options=options,
        )

        # Cache the response
        await set_cached_response(
            redis=redis,
            tenant_id=str(tenant.tenant_id),
            model=resolved,
            messages=request.messages,
            response=response,
        )

        await audit_write(
            tenant_id=tenant.tenant_id,
            event_type=AuditEvent.REQUEST_COMPLETED,
            payload={"model": resolved, "stream": False, "cache_hit": False},
            db=db,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("proxy_error", error=str(e), model=resolved)
        await audit_write(
            tenant_id=tenant.tenant_id,
            event_type=AuditEvent.REQUEST_FAILED,
            payload={"model": resolved, "error": str(e)},
            db=db,
        )
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")
