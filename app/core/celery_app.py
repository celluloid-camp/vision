"""Celery application configuration"""

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CELERY_QUEUE_NAME = os.getenv("CELERY_QUEUE_NAME", "celluloid_video_processing")
CELERY_TASK_TIMEOUT = int(os.getenv("CELERY_TASK_TIMEOUT", 3600))
CELERY_VISIBILITY_TIMEOUT = int(
    os.getenv("CELERY_VISIBILITY_TIMEOUT", max(CELERY_TASK_TIMEOUT + 300, 600))
)

celery_app = Celery(
    "celluloid_vision",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.core.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Do not ack tasks that fail/timeout; allow them to be redelivered.
    task_acks_on_failure_or_timeout=False,
    # Reserve one task per worker process to minimize in-memory unacked backlog.
    worker_prefetch_multiplier=1,
    # Redis broker: if a worker dies before ack, redeliver after visibility timeout.
    # Keep this >= max task runtime to avoid duplicate concurrent execution.
    broker_transport_options={"visibility_timeout": CELERY_VISIBILITY_TIMEOUT},
    task_default_queue=CELERY_QUEUE_NAME,
    result_expires=86400,  # Results expire after 24 hours
    # Soft limit lets the task catch SoftTimeLimitExceeded and clean up.
    # Hard limit (soft + 5 minutes) kills the process if cleanup stalls.
    task_soft_time_limit=CELERY_TASK_TIMEOUT,
    task_time_limit=CELERY_TASK_TIMEOUT + 300,
)
