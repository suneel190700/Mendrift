#!/usr/bin/env bash
# Render start command: seed MLflow once, then launch the API.
set -euo pipefail
export MLFLOW_TRACKING_URI="sqlite:///$(pwd)/mlflow.db"
export MENDRIFT_DATA_DIR="$(pwd)/data"
export MENDRIFT_DEMO="0"
if [ ! -f "mlflow.db" ]; then
  echo "[start] seeding MLflow registry..."
  python scripts/seed_demo.py || echo "[start] seed failed -- tools will fall back to fixtures"
else
  echo "[start] mlflow.db present, skipping seed"
fi
echo "[start] launching API on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
