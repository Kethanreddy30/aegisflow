"""
AegisFlow benchmark script.
Measures latency and cache hit rates.

Usage:
    uv run python scripts/benchmark.py --key <api_key>
"""
import asyncio
import argparse
import time
import statistics
import httpx

BASE_URL = "http://localhost:8000"

TEST_MESSAGES = [
    [{"role": "user", "content": "say hello in one word"}],
    [{"role": "user", "content": "what is 2 plus 2"}],
    [{"role": "user", "content": "name one programming language"}],
]


async def single_request(
    client: httpx.AsyncClient,
    api_key: str,
    messages: list,
    model: str = "qwen2.5-coder:3b",
) -> tuple[int, float]:
    """Returns (status_code, duration_ms)."""
    start = time.monotonic()
    resp = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"X-API-Key": api_key},
        json={"model": model, "messages": messages, "stream": False},
        timeout=60.0,
    )
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    return resp.status_code, duration_ms


async def run_benchmark(api_key: str):
    print(f"\n=== AegisFlow Benchmark ===")
    print(f"Target: {BASE_URL}\n")

    async with httpx.AsyncClient() as client:

        # ── Warm-up ───────────────────────────────────────────────────────────
        print("Warming up cache (3 requests)...")
        for messages in TEST_MESSAGES:
            status, ms = await single_request(client, api_key, messages)
            print(f"  warm-up: {ms}ms (status={status})")

        print()

        # ── Cold latency (unique messages) ────────────────────────────────────
        print("Measuring cold latency (cache miss)...")
        cold_latencies = []
        for i, messages in enumerate(TEST_MESSAGES):
            unique = [{"role": "user", "content": f"unique request {i} {time.time()}"}]
            status, ms = await single_request(client, api_key, unique)
            cold_latencies.append(ms)
            print(f"  cold [{i+1}]: {ms}ms")

        print()

        # ── Cache hit latency ─────────────────────────────────────────────────
        print("Measuring cache hit latency (same messages)...")
        cache_latencies = []
        for i, messages in enumerate(TEST_MESSAGES):
            status, ms = await single_request(client, api_key, messages)
            cache_latencies.append(ms)
            print(f"  cache hit [{i+1}]: {ms}ms")

        print()

        # ── Concurrent requests ───────────────────────────────────────────────
        print("Measuring concurrent cache hits (5 parallel)...")
        tasks = [
            single_request(client, api_key, TEST_MESSAGES[0])
            for _ in range(5)
        ]
        start = time.monotonic()
        results = await asyncio.gather(*tasks)
        total_ms = round((time.monotonic() - start) * 1000, 2)
        concurrent_latencies = [r[1] for r in results]
        print(f"  5 concurrent requests completed in {total_ms}ms")

        print()

        # ── Summary ───────────────────────────────────────────────────────────
        print("=== Results ===")
        print(f"Cold latency    p50: {statistics.median(cold_latencies):.0f}ms")
        print(f"Cold latency    p95: {sorted(cold_latencies)[int(len(cold_latencies)*0.95)]:.0f}ms" if len(cold_latencies) >= 2 else f"Cold latency   avg: {statistics.mean(cold_latencies):.0f}ms")
        print(f"Cache latency   p50: {statistics.median(cache_latencies):.0f}ms")
        print(f"Cache latency   min: {min(cache_latencies):.0f}ms")
        print(f"Cache speedup:       {statistics.mean(cold_latencies)/statistics.mean(cache_latencies):.1f}x faster")
        print(f"Concurrent p50:      {statistics.median(concurrent_latencies):.0f}ms")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, help="API key for benchmark tenant")
    args = parser.parse_args()
    asyncio.run(run_benchmark(args.key))
