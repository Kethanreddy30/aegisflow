import time
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

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
from gateway.streaming import stream_ollama_response, make_streaming_response
from registry.provider_registry import resolve_model

logger = structlog.get_logger()

proxy_router = APIRouter()

OLLAMA_BASE_URL = "http://localhost:11434"


def _get_ollama_model_name(model: str) -> str:
    """
    Strip provider prefix if present.
    'ollama/qwen2.5-coder:3b' -> 'qwen2.5-coder:3b'
    'qwen2.5-coder:3b' -> 'qwen2.5-coder:3b'
    """
    if model.startswith("ollama/"):
        return model[len("ollama/"):]
    return model


@proxy_router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    tenant: TenantConfigSchema = Depends(get_tenant_from_key),
    db: AsyncSession = Depends(get_db),
):
    structlog.contextvars.bind_contextvars(
        tenant_id=str(tenant.tenant_id),
        requested_model=request.model,
    )

    # ── Step 1: 3-tier model routing ─────────────────────────────────────────
    routing = resolve_model(tenant, request.model)

    # Audit remap event — non-negotiable per spec
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
    ollama_model = _get_ollama_model_name(resolved)

    # ── Step 2: Build Ollama payload ─────────────────────────────────────────
    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
    ]

    options = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.max_tokens is not None:
        options["num_predict"] = request.max_tokens
    if request.top_p is not None:
        options["top_p"] = request.top_p

    # ── Step 3: Call Ollama ───────────────────────────────────────────────────
    try:
        import httpx

        if request.stream:
            # Streaming path
            async def _stream_generator():
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
                                "ollama_error",
                                status=resp.status_code,
                                body=error_body.decode(),
                            )
                            yield f"data: {GatewayError.make('Ollama request failed').model_dump_json()}\n\n"
                            return

                        import json
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
                                from gateway.streaming import _make_chunk
                                chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                                yield _make_chunk(chunk_id, resolved, content)

                            if done:
                                from gateway.streaming import _make_chunk, _make_done
                                chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                                yield _make_chunk(chunk_id, resolved, "", finish_reason="stop")
                                yield _make_done()

                                await audit_write(
                                    tenant_id=tenant.tenant_id,
                                    event_type=AuditEvent.REQUEST_COMPLETED,
                                    payload={
                                        "model": resolved,
                                        "stream": True,
                                    },
                                    db=db,
                                )
                                return

            return make_streaming_response(_stream_generator())

        else:
            # Non-streaming path
            async with httpx.AsyncClient(timeout=120.0) as client:
                start = time.monotonic()
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": ollama_model,
                        "messages": messages,
                        "stream": False,
                        "options": options,
                    },
                )
                duration_ms = round((time.monotonic() - start) * 1000, 2)

            if resp.status_code != 200:
                logger.error(
                    "ollama_error",
                    status=resp.status_code,
                    body=resp.text,
                )
                raise HTTPException(
                    status_code=502,
                    detail="Upstream model request failed",
                )

            data = resp.json()
            content = data.get("message", {}).get("content", "")

            await audit_write(
                tenant_id=tenant.tenant_id,
                event_type=AuditEvent.REQUEST_COMPLETED,
                payload={
                    "model": resolved,
                    "stream": False,
                    "duration_ms": duration_ms,
                },
                db=db,
            )

            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
                created=int(time.time()),
                model=resolved,
                choices=[ChatChoice(
                    message=ChatMessageResponse(content=content),
                    finish_reason="stop",
                )],
                usage=UsageInfo(
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                ),
            )

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
