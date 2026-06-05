"""
Tenant isolation tests — the most critical test suite in AegisFlow.
These tests verify that no data leaks between tenants under any condition.
If any of these fail, the product has no security story.

Run: uv run pytest tests/integration/test_tenant_isolation.py -v
"""
import asyncio
import hashlib
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.auth import generate_api_key, hash_api_key
from control_plane.models import (
    Tenant, TenantPolicy, ApiKey,
    TenantConfigSchema, FailoverPolicySchema,
)
from db.session import AsyncSessionFactory


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    async with AsyncSessionFactory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def tenant_a(db):
    """Create an isolated test tenant A."""
    import uuid
    tenant = Tenant(
        name="Test Tenant A",
        slug=f"test-a-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(tenant)
    await db.flush()

    policy = TenantPolicy(
        tenant_id=tenant.tenant_id,
        masking_enabled=True,
    )
    db.add(policy)

    raw_key, key_hash = generate_api_key()
    api_key = ApiKey(
        key_hash=key_hash,
        tenant_id=tenant.tenant_id,
        label="test",
        status="active",
    )
    db.add(api_key)
    await db.commit()

    return {"tenant": tenant, "api_key": raw_key}


@pytest_asyncio.fixture
async def tenant_b(db):
    """Create an isolated test tenant B."""
    import uuid
    tenant = Tenant(
        name="Test Tenant B",
        slug=f"test-b-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(tenant)
    await db.flush()

    policy = TenantPolicy(
        tenant_id=tenant.tenant_id,
        masking_enabled=True,
    )
    db.add(policy)

    raw_key, key_hash = generate_api_key()
    api_key = ApiKey(
        key_hash=key_hash,
        tenant_id=tenant.tenant_id,
        label="test",
        status="active",
    )
    db.add(api_key)
    await db.commit()

    return {"tenant": tenant, "api_key": raw_key}


# ── Auth Isolation Tests ───────────────────────────────────────────────────────

class TestAuthIsolation:

    @pytest.mark.asyncio
    async def test_tenant_a_key_cannot_authenticate_as_tenant_b(
        self, tenant_a, tenant_b
    ):
        """Tenant A's API key must never resolve to Tenant B's config."""
        from control_plane.auth import load_tenant_config, hash_api_key
        from sqlalchemy import select
        from control_plane.models import ApiKey

        async with AsyncSessionFactory() as db:
            key_hash = hash_api_key(tenant_a["api_key"])
            result = await db.execute(
                select(ApiKey).where(ApiKey.key_hash == key_hash)
            )
            row = result.scalar_one_or_none()
            assert row is not None
            assert row.tenant_id == tenant_a["tenant"].tenant_id
            assert row.tenant_id != tenant_b["tenant"].tenant_id

    @pytest.mark.asyncio
    async def test_invalid_key_returns_none(self):
        """Completely invalid key must not resolve to any tenant."""
        from sqlalchemy import select
        from control_plane.models import ApiKey
        from control_plane.auth import hash_api_key

        fake_hash = hash_api_key("af_totallyFakeKey123456789")
        async with AsyncSessionFactory() as db:
            result = await db.execute(
                select(ApiKey).where(ApiKey.key_hash == fake_hash)
            )
            row = result.scalar_one_or_none()
            assert row is None

    @pytest.mark.asyncio
    async def test_each_tenant_has_unique_api_key_hash(
        self, tenant_a, tenant_b
    ):
        """Two tenants must never share the same key hash."""
        hash_a = hash_api_key(tenant_a["api_key"])
        hash_b = hash_api_key(tenant_b["api_key"])
        assert hash_a != hash_b


# ── Redis Cache Isolation Tests ───────────────────────────────────────────────

class TestCacheIsolation:

    @pytest.mark.asyncio
    async def test_cache_keys_are_tenant_scoped(self, tenant_a, tenant_b):
        """Cache keys for the same query must differ between tenants."""
        from cache.keys import make_cache_key

        from gateway.schemas import ChatMessage
        query = [ChatMessage(role="user", content="What is the capital of France?")]
        model = "ollama/qwen2.5-coder:3b"

        key_a = make_cache_key(
            str(tenant_a["tenant"].tenant_id), model, query
        )
        key_b = make_cache_key(
            str(tenant_b["tenant"].tenant_id), model, query
        )

        assert key_a != key_b
        assert str(tenant_a["tenant"].tenant_id) in key_a
        assert str(tenant_b["tenant"].tenant_id) in key_b
        assert key_a.startswith("tenant:")
        assert key_b.startswith("tenant:")

    @pytest.mark.asyncio
    async def test_tenant_a_cache_not_readable_by_tenant_b(
        self, tenant_a, tenant_b
    ):
        """Tenant A's cached response must be invisible to Tenant B."""
        from redis.asyncio import from_url
        import os
        from cache.keys import make_cache_key

        redis = from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )

        model = "ollama/qwen2.5-coder:3b"
        from gateway.schemas import ChatMessage
        query = [ChatMessage(role="user", content="isolation test query unique 99821")]

        key_a = make_cache_key(
            str(tenant_a["tenant"].tenant_id), model, query
        )
        key_b = make_cache_key(
            str(tenant_b["tenant"].tenant_id), model, query
        )

        # Write to tenant A's cache
        await redis.set(key_a, '{"test": "response_a"}', ex=60)

        # Tenant B's key must return nothing
        val_b = await redis.get(key_b)
        assert val_b is None, "Tenant B can read Tenant A's cache — ISOLATION FAILURE"

        # Tenant A's key must return the value
        val_a = await redis.get(key_a)
        assert val_a is not None

        # Cleanup
        await redis.delete(key_a)
        await redis.aclose()


# ── Masking Isolation Tests ────────────────────────────────────────────────────

class TestMaskingIsolation:

    @pytest.mark.asyncio
    async def test_mask_tokens_are_tenant_scoped(self, tenant_a, tenant_b):
        """Same PII value must produce different tokens for different tenants."""
        from masking.tokenizer import mask_text
        from masking.detector import detect

        pii_text = "Contact john@example.com for details"
        matches = detect(pii_text)

        masked_a, token_map_a = mask_text(
            pii_text, matches, str(tenant_a["tenant"].tenant_id)
        )
        masked_b, token_map_b = mask_text(
            pii_text, matches, str(tenant_b["tenant"].tenant_id)
        )

        token_a = list(token_map_a.keys())[0]
        token_b = list(token_map_b.keys())[0]

        assert token_a != token_b, (
            "Same PII produces same token for different tenants — "
            "cross-tenant reconstruction possible"
        )

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_reconstruct_tenant_a_tokens(
        self, tenant_a, tenant_b
    ):
        """Tenant B must not be able to reconstruct Tenant A's masked values."""
        from redis.asyncio import from_url
        import os
        from masking.store import MaskStore
        from masking.tokenizer import mask_text
        from masking.detector import detect

        redis = from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
        store = MaskStore(redis)

        pii_text = "Call me at 555-123-4567 please"
        matches = detect(pii_text)
        tenant_a_id = str(tenant_a["tenant"].tenant_id)
        tenant_b_id = str(tenant_b["tenant"].tenant_id)

        # Tenant A masks and stores
        _, token_map = mask_text(pii_text, matches, tenant_a_id)
        await store.save_many(token_map, tenant_a_id)

        # Tenant B tries to restore Tenant A's token
        token = list(token_map.keys())[0]
        result = await store.restore(token, tenant_b_id)

        assert result is None, (
            f"Tenant B reconstructed Tenant A's PII token — "
            f"CRITICAL ISOLATION FAILURE: {result}"
        )

        await redis.aclose()

    @pytest.mark.asyncio
    async def test_mask_store_keys_are_tenant_namespaced(
        self, tenant_a, tenant_b
    ):
        """Verify mask store keys include tenant_id in namespace."""
        from masking.store import MaskStore
        from redis.asyncio import from_url
        import os

        redis = from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
        store = MaskStore(redis)

        tenant_a_id = str(tenant_a["tenant"].tenant_id)
        token = "__MASK_EMAIL_ABCD1234__"

        key = store._key(token, tenant_a_id)
        assert key.startswith(f"tenant:{tenant_a_id}:mask:")
        assert token in key

        await redis.aclose()


# ── Audit Log Isolation Tests ─────────────────────────────────────────────────

class TestAuditIsolation:

    @pytest.mark.asyncio
    async def test_audit_events_are_tenant_scoped(
        self, tenant_a, tenant_b, db
    ):
        """Audit events written for Tenant A must not appear in Tenant B's log."""
        from control_plane.audit import write as audit_write, AuditEvent
        from sqlalchemy import select
        from control_plane.models import AuditLog

        await audit_write(
            tenant_id=tenant_a["tenant"].tenant_id,
            event_type=AuditEvent.REQUEST_COMPLETED,
            payload={"test": "tenant_a_event"},
            db=db,
        )
        await db.flush()

        # Query Tenant B's audit log
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_b["tenant"].tenant_id,
                AuditLog.event_type == AuditEvent.REQUEST_COMPLETED,
            )
        )
        tenant_b_events = result.scalars().all()

        # Tenant B must have zero events from Tenant A's write
        for event in tenant_b_events:
            assert event.tenant_id == tenant_b["tenant"].tenant_id
            assert event.payload != {"test": "tenant_a_event"}, (
                "Tenant A's audit event visible in Tenant B's log — ISOLATION FAILURE"
            )


# ── Concurrent Request Isolation ──────────────────────────────────────────────

class TestConcurrentIsolation:

    @pytest.mark.asyncio
    async def test_concurrent_cache_writes_dont_mix(
        self, tenant_a, tenant_b
    ):
        """Simultaneous cache writes from two tenants must not cross-contaminate."""
        from redis.asyncio import from_url
        import os
        from cache.keys import make_cache_key

        redis = from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )

        model = "ollama/qwen2.5-coder:3b"
        from gateway.schemas import ChatMessage
        query = [ChatMessage(role="user", content="concurrent isolation test query 55512")]

        key_a = make_cache_key(
            str(tenant_a["tenant"].tenant_id), model, query
        )
        key_b = make_cache_key(
            str(tenant_b["tenant"].tenant_id), model, query
        )

        # Write both concurrently
        await asyncio.gather(
            redis.set(key_a, "response_for_tenant_a", ex=60),
            redis.set(key_b, "response_for_tenant_b", ex=60),
        )

        # Read both — must be independent
        val_a, val_b = await asyncio.gather(
            redis.get(key_a),
            redis.get(key_b),
        )

        assert val_a == "response_for_tenant_a", "Tenant A cache corrupted"
        assert val_b == "response_for_tenant_b", "Tenant B cache corrupted"
        assert val_a != val_b, "Tenant caches mixed under concurrent writes"

        await asyncio.gather(redis.delete(key_a), redis.delete(key_b))
        await redis.aclose()
