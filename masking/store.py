import json
import logging
from typing import Dict, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

TTL_SECONDS = 300  # 5 minutes — enough for any inference chain


class MaskStore:
    """
    Tenant-scoped ephemeral store for PII tokens.
    Keys expire after TTL_SECONDS.
    Tenant isolation is enforced by key namespace.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    def _key(self, token: str, tenant_id: str) -> str:
        return f"tenant:{tenant_id}:mask:{token}"

    async def save_many(
        self,
        token_map: Dict[str, str],
        tenant_id: str,
    ) -> None:
        """Save all tokens from a single request in one pipeline."""
        if not token_map:
            return
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for token, original in token_map.items():
                    key = self._key(token, tenant_id)
                    pipe.set(key, original, ex=TTL_SECONDS)
                await pipe.execute()
        except Exception as e:
            # Non-critical write failure — log and continue
            # Reconstruction will fail gracefully if tokens are missing
            logger.warning(
                f"MaskStore.save_many failed: tenant={tenant_id} "
                f"tokens={len(token_map)} error={e}"
            )

    async def restore(self, token: str, tenant_id: str) -> Optional[str]:
        """Retrieve original value for a single token."""
        try:
            key = self._key(token, tenant_id)
            value = await self._redis.get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception as e:
            logger.warning(
                f"MaskStore.restore failed: tenant={tenant_id} "
                f"token={token} error={e}"
            )
            return None

    async def restore_all(self, text: str, tenant_id: str) -> str:
        """
        Find all mask tokens in text and replace with originals.
        Tokens not found in Redis are left as-is (TTL expired or
        hallucinated suffix — both safe to leave).
        """
        import re
        MASK_PATTERN = re.compile(r'__MASK_[A-Z]+_[A-F0-9]{8}__')
        tokens = MASK_PATTERN.findall(text)

        if not tokens:
            return text

        for token in set(tokens):  # deduplicate
            original = await self.restore(token, tenant_id)
            if original:
                text = text.replace(token, original)
            else:
                logger.warning(
                    f"MaskStore: token not found (expired or hallucinated) "
                    f"tenant={tenant_id} token={token}"
                )
        return text
