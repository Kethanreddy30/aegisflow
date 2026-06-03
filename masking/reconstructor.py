import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Strict pattern — only exact format matches
# Hallucinated suffixes like __MASK_EMAIL_7A91B3C2__1 do NOT match
MASK_PATTERN = re.compile(r'__MASK_[A-Z]+_[A-F0-9]{8}__')


def find_tokens(text: str) -> list[str]:
    """Return all valid mask tokens found in text."""
    return MASK_PATTERN.findall(text)


def has_tokens(text: str) -> bool:
    """Fast check — are any mask tokens present?"""
    return bool(MASK_PATTERN.search(text))


async def reconstruct(
    text: str,
    tenant_id: str,
    store,  # MaskStore — avoid circular import
) -> str:
    """
    Replace all mask tokens in text with original PII values.
    Tokens not found in store are left as-is — never silently corrupt output.
    """
    if not has_tokens(text):
        return text

    return await store.restore_all(text, tenant_id)


def reconstruct_sync(
    text: str,
    token_map: dict[str, str],
) -> str:
    """
    Synchronous reconstruction from an in-memory token_map.
    Used when Redis is not available or for testing.
    """
    tokens = find_tokens(text)
    for token in set(tokens):
        original = token_map.get(token)
        if original:
            text = text.replace(token, original)
        else:
            logger.warning(f"reconstruct_sync: token not found: {token}")
    return text
