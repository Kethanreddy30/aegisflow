#!/bin/bash
# AegisFlow — one-command demo start
# Usage: bash scripts/start_demo.sh

set -e

echo ""
echo "=== AegisFlow Demo ==="
echo ""

# 1. Start infrastructure
echo "Starting PostgreSQL + Redis..."
docker compose -f infra/docker-compose.yml up -d
sleep 2

# 2. Run migrations
echo "Running migrations..."
uv run alembic upgrade head

# 3. Seed demo tenants
echo "Seeding demo tenants..."
uv run python db/seed.py

# 4. Start gateway
echo ""
echo "Starting AegisFlow gateway..."
echo "Docs:    http://localhost:8000/docs"
echo "Metrics: http://localhost:8000/metrics"
echo "Redis:   http://localhost:8001"
echo ""
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000
