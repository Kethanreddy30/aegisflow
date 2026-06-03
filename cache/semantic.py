import json
import structlog
from typing import Optional
from redis.asyncio import Redis
from cache.keys import make_cache_key
from gateway.schemas import ChatCompletionResponse, ChatMessage

logger = structlog.get_logger()

# TTL for cached responses — 1 hour default
CACHE_TTL_SECONDS = 3600


async def get_cached_response(
    redis: Redis,
    tenant_id: str,
    model: str,
    messages: list[ChatMessage],
) -> Optional[ChatCompletionResponse]:
    """
    Exact hash lookup. Returns cached response or None.
    Cache miss is the normal path — never block on cache failure.
    """
    try:
        key = make_cache_key(tenant_id, model, messages)
        raw = await redis.get(key)
        if not raw:
            return None
        logger.info("cache_hit", tenant_id=tenant_id, model=model, key=key)
        return ChatCompletionResponse.model_validate_json(raw)
    except Exception as e:
        # Cache failure must never break inference
        logger.warning("cache_get_failed", error=str(e))
        return None


async def set_cached_response(
    redis: Redis,
    tenant_id: str,
    model: str,
    messages: list[ChatMessage],
    response: ChatCompletionResponse,
    ttl: int = CACHE_TTL_SECONDS,
) -> None:
    """
    Store response in cache with TTL.
    Fire and forget — never raise on cache write failure.
    """
    try:
        key = make_cache_key(tenant_id, model, messages)
        await redis.set(key, response.model_dump_json(), ex=ttl)
        logger.info("cache_set", tenant_id=tenant_id, model=model, key=key, ttl=ttl)
    except Exception as e:
        logger.warning("cache_set_failed", error=str(e))


async def invalidate_tenant_cache(
    redis: Redis,
    tenant_id: str,
) -> int:
    """
    Invalidate all cached responses for a tenant.
    Returns number of keys deleted.
    """
    try:
        pattern = f"tenant:{tenant_id}:cache:*"
        keys = await redis.keys(pattern)
        if not keys:
            return 0
        deleted = await redis.delete(*keys)
        logger.info("cache_invalidated", tenant_id=tenant_id, deleted=deleted)
        return deleted
    except Exception as e:
        logger.warning("cache_invalidation_failed", error=str(e))
        return 0
