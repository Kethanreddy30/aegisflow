import hashlib
import json
from typing import List
from gateway.schemas import ChatMessage


def make_cache_key(
    tenant_id: str,
    model: str,
    messages: List[ChatMessage],
) -> str:
    """
    Build a deterministic tenant-namespaced cache key.
    Same tenant + same model + same messages = same key.
    Different tenants always produce different keys.

    Format: tenant:{tenant_id}:cache:{hash}
    """
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
        },
        sort_keys=True,
    )
    content_hash = hashlib.sha256(payload.encode()).hexdigest()[:32]
    return f"tenant:{tenant_id}:cache:{content_hash}"


def make_budget_key(tenant_id: str, month: str) -> str:
    """Format: tenant:{tenant_id}:budget:{YYYY-MM}"""
    return f"tenant:{tenant_id}:budget:{month}"


def make_ratelimit_key(tenant_id: str, provider: str, window: str) -> str:
    """Format: tenant:{tenant_id}:ratelimit:{provider}:{window}"""
    return f"tenant:{tenant_id}:ratelimit:{provider}:{window}"
