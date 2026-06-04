"""
Demo tenant bootstrap script.
Run once after docker compose up to create two demo tenants.
Usage: uv run python scripts/seed_tenant.py
"""
import asyncio
import httpx

BASE_URL = "http://localhost:8000"

TENANTS = [
    {
        "name": "Acme Finance",
        "slug": "acme-finance",
        "masking_enabled": True,
    },
    {
        "name": "Beta Legal",
        "slug": "beta-legal",
        "masking_enabled": True,
    },
]


async def seed():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:

        # Health check first
        r = await client.get("/health")
        assert r.status_code == 200, f"Gateway not ready: {r.text}"
        print(f"Gateway: {r.json()['status']}")

        for t in TENANTS:
            r = await client.post("/tenant/create", json=t)
            if r.status_code == 200:
                data = r.json()
                print(f"\nTenant: {data['slug']}")
                print(f"  ID:      {data['tenant_id']}")
                print(f"  API Key: {data['api_key']}")
                print(f"  >>> Save this key — it won't be shown again <<<")
            elif r.status_code == 409:
                print(f"\nTenant '{t['slug']}' already exists — skipping")
            else:
                print(f"\nFailed to create '{t['slug']}': {r.text}")

        print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
