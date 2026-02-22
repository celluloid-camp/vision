#!/bin/sh
# Entrypoint: run api, worker, or both depending on first argument.
# Usage: docker run ... [api|worker|both]
#   both   (default) - run Celery worker in background + uvicorn in foreground
#   api    - run uvicorn only
#   worker - run Celery worker only

set -e

CELERY_QUEUE="${CELERY_QUEUE_NAME:-celluloid_video_processing}"

run_api() {
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8081
}

run_worker() {
  exec python -m celery -A app.core.celery_app worker \
    --loglevel=info \
    --queues="${CELERY_QUEUE}" \
    --concurrency=1
}

run_both() {
  python -m celery -A app.core.celery_app worker \
    --loglevel=info \
    --queues="${CELERY_QUEUE}" \
    --concurrency=1 &
  WORKER_PID=$!
  trap 'kill $WORKER_PID 2>/dev/null || true; exit' TERM INT
  # Run uvicorn in foreground (no exec) so trap can kill worker on shutdown
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8081
}

case "${1:-both}" in
  api)    run_api ;;
  worker) run_worker ;;
  both)   run_both ;;
  *)
    echo "Usage: $0 {api|worker|both}" >&2
    echo "  both   - run worker + api in one container (default)" >&2
    echo "  api    - run FastAPI (uvicorn) only" >&2
    echo "  worker - run Celery worker only" >&2
    exit 1
    ;;
esac
