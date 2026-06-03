import hashlib
from typing import Dict, List, Tuple

from masking.detector import PIIMatch


def _make_token(pii_type: str, value: str, tenant_id: str) -> str:
    """
    Deterministic token — same value + tenant always produces same token.
    Prevents duplicate masking of the same PII in one request.
    Format: __MASK_{TYPE}_{8_HEX}__
    """
    seed = f"{tenant_id}:{pii_type}:{value}"
    hex_suffix = hashlib.sha256(seed.encode()).hexdigest()[:8].upper()
    return f"__MASK_{pii_type}_{hex_suffix}__"


def mask_text(
    text: str,
    matches: List[PIIMatch],
    tenant_id: str,
) -> Tuple[str, Dict[str, str]]:
    """
    Replace PII in text with deterministic tokens.

    Returns:
        masked_text   — text with PII replaced
        token_map     — {token: original_value} for reconstruction

    Replaces from END to START to preserve string offsets.
    """
    if not matches:
        return text, {}

    token_map: Dict[str, str] = {}

    # Process end → start to keep offsets valid
    for match in reversed(matches):
        token = _make_token(
            pii_type=match.pii_type.value,
            value=match.value,
            tenant_id=tenant_id,
        )
        token_map[token] = match.value
        text = text[:match.start] + token + text[match.end:]

    return text, token_map


def mask_messages(
    messages: List[dict],
    tenant_id: str,
) -> Tuple[List[dict], Dict[str, str]]:
    """
    Mask PII across all user messages.
    Skips system messages — system prompts may contain intentional
    structured data. Only masks role=user content.

    Returns:
        masked_messages — copy of messages with PII replaced
        token_map       — combined token map for all messages
    """
    from masking.detector import detect

    combined_token_map: Dict[str, str] = {}
    masked = []

    for msg in messages:
        if msg.get("role") != "user":
            masked.append(msg)
            continue

        content = msg.get("content", "")
        if not isinstance(content, str):
            # Skip non-text content (future multimodal support)
            masked.append(msg)
            continue

        matches = detect(content)
        if not matches:
            masked.append(msg)
            continue

        masked_content, token_map = mask_text(content, matches, tenant_id)
        combined_token_map.update(token_map)
        masked.append({**msg, "content": masked_content})

    return masked, combined_token_map
