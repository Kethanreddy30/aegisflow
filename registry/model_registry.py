import json
import structlog
from typing import Optional
from redis.asyncio import Redis

logger = structlog.get_logger()

# Redis key pattern: registry:model:{model_name}
# Value: JSON with provider + model metadata
_KEY_PREFIX = "registry:model:"


def _model_key(model_name: str) -> str:
    return f"{_KEY_PREFIX}{model_name}"


async def register_model(
    redis: Redis,
    model_name: str,
    provider: str,
    endpoint: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Register a model in the registry.
    Hot-swappable — no restart required.
    """
    payload = {
        "model_name": model_name,
        "provider": provider,
        "endpoint": endpoint or "",
        "metadata": metadata or {},
        "status": "healthy",
    }
    await redis.set(_model_key(model_name), json.dumps(payload))
    logger.info("model_registered", model=model_name, provider=provider)


async def get_model(
    redis: Redis,
    model_name: str,
) -> Optional[dict]:
    """
    Resolve a model by name.
    Returns None if not registered.
    """
    raw = await redis.get(_model_key(model_name))
    if not raw:
        return None
    return json.loads(raw)


async def deregister_model(
    redis: Redis,
    model_name: str,
) -> None:
    """Remove a model from the registry."""
    await redis.delete(_model_key(model_name))
    logger.info("model_deregistered", model=model_name)


async def list_models(redis: Redis) -> list[dict]:
    """List all registered models."""
    keys = await redis.keys(f"{_KEY_PREFIX}*")
    if not keys:
        return []
    values = await redis.mget(*keys)
    return [json.loads(v) for v in values if v]


async def set_model_status(
    redis: Redis,
    model_name: str,
    status: str,
) -> None:
    """
    Update model health status in-place.
    status: 'healthy' | 'degraded' | 'offline'
    """
    raw = await redis.get(_model_key(model_name))
    if not raw:
        logger.warning("model_not_found_for_status_update", model=model_name)
        return
    payload = json.loads(raw)
    payload["status"] = status
    await redis.set(_model_key(model_name), json.dumps(payload))
    logger.info("model_status_updated", model=model_name, status=status)
