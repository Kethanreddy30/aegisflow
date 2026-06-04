from prometheus_client import Counter, Histogram, Gauge

# ── Request Metrics ───────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "aegisflow_requests_total",
    "Total inference requests",
    ["tenant_id", "model", "stream", "cache_hit"],
)
REQUEST_LATENCY = Histogram(
    "aegisflow_request_duration_seconds",
    "Inference request latency",
    ["tenant_id", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
REQUEST_ERRORS = Counter(
    "aegisflow_request_errors_total",
    "Total failed inference requests",
    ["tenant_id", "model", "error_type"],
)

# ── Cache Metrics ─────────────────────────────────────────────────────────────
CACHE_HITS = Counter(
    "aegisflow_cache_hits_total",
    "Total cache hits",
    ["tenant_id", "model"],
)
CACHE_MISSES = Counter(
    "aegisflow_cache_misses_total",
    "Total cache misses",
    ["tenant_id", "model"],
)

# ── Masking Metrics ───────────────────────────────────────────────────────────
MASKING_APPLIED = Counter(
    "aegisflow_masking_applied_total",
    "Total requests where PII masking was applied",
    ["tenant_id"],
)
TOKENS_MASKED = Counter(
    "aegisflow_tokens_masked_total",
    "Total PII tokens masked",
    ["tenant_id", "pii_type"],
)

# ── Provider Metrics ──────────────────────────────────────────────────────────
PROVIDER_FAILOVERS = Counter(
    "aegisflow_provider_failovers_total",
    "Total provider failover events",
    ["tenant_id", "from_provider", "to_provider"],
)
PROVIDER_ERRORS = Counter(
    "aegisflow_provider_errors_total",
    "Total provider call failures",
    ["tenant_id", "provider"],
)

# ── System Metrics ────────────────────────────────────────────────────────────
ACTIVE_TENANTS = Gauge(
    "aegisflow_active_tenants",
    "Number of active tenants",
)
