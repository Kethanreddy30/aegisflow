import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models import AuditLog


async def write(
    tenant_id: uuid.UUID,
    event_type: str,
    payload: Optional[Dict[str, Any]],
    db: AsyncSession,
) -> None:
    """
    Append-only audit log writer.
    Never update or delete from audit_log.
    """
    entry = AuditLog(
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(entry)
    await db.flush()


# Event type constants — use these everywhere, never raw strings
class AuditEvent:
    TENANT_CREATED       = "tenant.created"
    PROVIDER_REGISTERED  = "tenant.provider.registered"
    KEY_EXHAUSTED        = "provider.key_exhausted"
    PROVIDER_FAILOVER    = "provider.failover"
    MASKING_APPLIED      = "security.masking_applied"
    REQUEST_COMPLETED    = "request.completed"
    REQUEST_FAILED       = "request.failed"
    POLICY_UPDATED       = "tenant.policy_updated"
