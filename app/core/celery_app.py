"""Celery application configuration"""
import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CELERY_QUEUE_NAME = os.getenv("CELERY_QUEUE_NAME", "celluloid_video_processing")
CELERY_TASK_TIMEOUT = int(os.getenv("CELERY_TASK_TIMEOUT", 3600))

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
    task_default_queue=CELERY_QUEUE_NAME,
    result_expires=86400,  # Results expire after 24 hours
)
