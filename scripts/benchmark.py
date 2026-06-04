"""
Latency + cache hit benchmark.
Usage: uv run python scripts/benchmark.py --key <api_key>
"""
import asyncio
import argparse
import time
import httpx

BASE_URL = "http://localhost:8000"

TEST_CASES = [
    ("trivial",   "Fix the grammar: 'she dont know nothing'"),
    ("moderate",  "Write a Python function to validate an email address"),
    ("complex",   "Design a rate limiting system for a multi-tenant API"),
]


async def run(api_key: str):
    headers = {"X-API-Key": api_key}
    results = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:

        # Cold pass
        print("Cold pass (no cache)...")
        for tier, prompt in TEST_CASES:
            start = time.monotonic()
            r = await client.post(
                "/v1/chat/completions",
                headers=headers,
                json={"model": "ollama/qwen2.5-coder:3b",
                      "messages": [{"role": "user", "content": prompt}]},
            )
            latency = round((time.monotonic() - start) * 1000)
            results.append({
                "tier": tier, "latency_ms": latency,
                "cached": False, "status": r.status_code
            })
            print(f"  {tier:10} {latency:6}ms  status={r.status_code}")

        # Warm pass
        print("\nWarm pass (cache)...")
        for tier, prompt in TEST_CASES:
            start = time.monotonic()
            r = await client.post(
                "/v1/chat/completions",
                headers=headers,
                json={"model": "ollama/qwen2.5-coder:3b",
                      "messages": [{"role": "user", "content": prompt}]},
            )
            latency = round((time.monotonic() - start) * 1000)
            results.append({
                "tier": tier, "latency_ms": latency,
                "cached": True, "status": r.status_code
            })
            print(f"  {tier:10} {latency:6}ms  status={r.status_code}")

    # Summary
    cold  = [r for r in results if not r["cached"]]
    warm  = [r for r in results if r["cached"]]
    cache_hit_rate = sum(
        1 for w in warm if w["latency_ms"] < 500
    ) / len(warm) * 100

    print(f"\n{'─'*40}")
    print(f"Cold avg:       {sum(r['latency_ms'] for r in cold)  // len(cold)}ms")
    print(f"Warm avg:       {sum(r['latency_ms'] for r in warm)  // len(warm)}ms")
    print(f"Cache hit rate: ~{cache_hit_rate:.0f}%")
    print(f"{'─'*40}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, help="Tenant API key")
    args = parser.parse_args()
    asyncio.run(run(args.key))
