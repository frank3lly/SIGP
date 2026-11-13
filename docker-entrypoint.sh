#!/usr/bin/env bash
set -e

# Ensure storage directories exist
mkdir -p /workspace/storage/images
mkdir -p /workspace/tests/output
mkdir -p /workspace/tests/reports

PORT="${PORT:-8000}"

case "$1" in
  server)
    echo "[Parqueame Docker] Starting FastAPI production server on 0.0.0.0:${PORT}..."
    exec uvicorn server.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
    ;;
  simulate)
    echo "[Parqueame Docker] Launching multi-camera simulator..."
    shift
    exec python simulation/simulate_cameras.py --server-url http://localhost:8000 "$@"
    ;;
  test)
    echo "[Parqueame Docker] Executing end-to-end integration and detection test..."
    shift
    exec python tests/test_end_to_end.py "$@"
    ;;
  benchmark)
    echo "[Parqueame Docker] Executing stress and VRAM benchmark..."
    shift
    exec python tests/test_stress_benchmark.py "$@"
    ;;
  soak)
    echo "[Parqueame Docker] Executing continuous soak test..."
    shift
    exec python tools/run_soak_test.py "$@"
    ;;
  *)
    # Arbitrary command passthrough
    exec "$@"
    ;;
esac
