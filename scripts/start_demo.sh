#!/bin/bash
set -e

echo "Starting AegisFlow demo stack..."
cd "$(dirname "$0")/.."

# Start infrastructure
docker compose -f infra/docker-compose.yml up -d --build

echo "Waiting for services..."
sleep 10

# Pull Ollama model if not present
echo "Pulling qwen2.5-coder:3b..."
docker compose -f infra/docker-compose.yml exec ollama \
  ollama pull qwen2.5-coder:3b

# Run migrations
echo "Running migrations..."
uv run alembic upgrade head

# Seed demo tenants
echo "Seeding demo tenants..."
uv run python scripts/seed_tenant.py

echo ""
echo "AegisFlow running:"
echo "  Gateway:      http://localhost:8000"
echo "  Docs:         http://localhost:8000/docs"
echo "  Metrics:      http://localhost:8000/metrics"
echo "  Prometheus:   http://localhost:9090"
echo "  Grafana:      http://localhost:3000  (admin / aegisflow)"
echo "  RedisInsight: http://localhost:8001"
