"""
Demo seed script — creates realistic tenants for demonstration.
Run once after migrations. Safe to run multiple times (idempotent).

Usage:
    uv run python db/seed.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from db.session import AsyncSessionFactory
from control_plane.models import (
    Tenant, TenantPolicy, TenantProvider, ApiKey
)
from control_plane.auth import generate_api_key
from control_plane.audit import write as audit_write, AuditEvent
from sqlalchemy import select


DEMO_TENANTS = [
    {
        "name": "Acme Legal LLP",
        "slug": "acme-legal",
        "masking_enabled": True,
        "allowed_models": ["qwen2.5-coder:3b"],
        "fallback_model": "qwen2.5-coder:3b",
        "providers": [],
    },
    {
        "name": "Regional Bank Demo",
        "slug": "regional-bank",
        "masking_enabled": True,
        "allowed_models": [],
        "fallback_model": "qwen2.5-coder:3b",
        "providers": [],
    },
    {
        "name": "Healthcare Startup",
        "slug": "healthcare-startup",
        "masking_enabled": True,
        "allowed_models": ["qwen2.5-coder:3b"],
        "fallback_model": None,
        "providers": [],
    },
]


async def seed():
    async with AsyncSessionFactory() as db:
        print("\n=== AegisFlow Demo Seed ===\n")

        for tenant_data in DEMO_TENANTS:
            # Check if already exists
            existing = await db.execute(
                select(Tenant).where(Tenant.slug == tenant_data["slug"])
            )
            if existing.scalar_one_or_none():
                print(f"⏭  {tenant_data['slug']} — already exists, skipping")
                continue

            # Create tenant
            tenant = Tenant(
                name=tenant_data["name"],
                slug=tenant_data["slug"],
                status="active",
            )
            db.add(tenant)
            await db.flush()

            # Create policy
            policy = TenantPolicy(
                tenant_id=tenant.tenant_id,
                masking_enabled=tenant_data["masking_enabled"],
                allowed_models=tenant_data["allowed_models"],
                fallback_model=tenant_data["fallback_model"],
                auto_failover=True,
                notify_admin=True,
                fallback_to_local=True,
            )
            db.add(policy)
            await db.flush()

            # Create API key
            raw_key, key_hash = generate_api_key()
            api_key_row = ApiKey(
                key_hash=key_hash,
                tenant_id=tenant.tenant_id,
                label="demo",
                status="active",
            )
            db.add(api_key_row)
            await db.flush()

            await audit_write(
                tenant_id=tenant.tenant_id,
                event_type=AuditEvent.TENANT_CREATED,
                payload={"name": tenant_data["name"], "seeded": True},
                db=db,
            )

            await db.commit()

            print(f"✅ {tenant_data['name']}")
            print(f"   slug:     {tenant_data['slug']}")
            print(f"   masking:  {tenant_data['masking_enabled']}")
            print(f"   api_key:  {raw_key}")
            print()

        print("=== Seed complete ===\n")


if __name__ == "__main__":
    asyncio.run(seed())
