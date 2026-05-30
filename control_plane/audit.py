import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.models import AuditLog

logger = logging.getLogger(__name__)


async def write(
    tenant_id: uuid.UUID,
    event_type: str,
    payload: Optional[Dict[str, Any]],
    db: AsyncSession,
) -> None:
    """
    Append-only audit log writer.
    Resilient — failure logs a warning but never crashes the calling operation.
    Never update or delete from audit_log.
    """
    try:
        entry = AuditLog(
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
        )
        db.add(entry)
        await db.flush()
    except Exception as e:
        logger.warning(
            f"Audit write failed — event not recorded: "
            f"tenant={tenant_id} event={event_type} error={e}"
        )


class AuditEvent:
    TENANT_CREATED      = "tenant.created"
    PROVIDER_REGISTERED = "tenant.provider.registered"
    KEY_EXHAUSTED       = "provider.key_exhausted"
    PROVIDER_FAILOVER   = "provider.failover"
    MASKING_APPLIED     = "security.masking_applied"
    REQUEST_COMPLETED   = "request.completed"
    REQUEST_FAILED      = "request.failed"
    POLICY_UPDATED      = "tenant.policy_updated"
