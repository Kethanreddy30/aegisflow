import structlog
from redis.asyncio import Redis
from registry.model_registry import list_models, set_model_status

logger = structlog.get_logger()


async def check_ollama_health(endpoint: str) -> bool:
    """
    Ping Ollama API to verify model is reachable.
    Returns True if healthy, False otherwise.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{endpoint}/api/tags")
            return response.status_code == 200
    except Exception as e:
        logger.warning("ollama_health_check_failed", endpoint=endpoint, error=str(e))
        return False


async def refresh_model_health(redis: Redis) -> None:
    """
    Check health of all registered models.
    Updates status in registry.
    Called on startup and periodically.
    """
    models = await list_models(redis)
    for model in models:
        if model.get("provider") == "ollama":
            endpoint = model.get("endpoint", "http://localhost:11434")
            healthy = await check_ollama_health(endpoint)
            status = "healthy" if healthy else "offline"
            await set_model_status(redis, model["model_name"], status)
            logger.info(
                "model_health_refreshed",
                model=model["model_name"],
                status=status,
            )
