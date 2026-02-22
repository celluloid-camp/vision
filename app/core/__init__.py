"""Core application logic and configuration"""
from app.core.config import API_KEY, API_VERSION, HOST, PORT, REDIS_URL, MAX_WORKERS
from app.core.dependencies import job_manager
from app.core.background import (
    process_video_in_process,
    shutdown_process_pool,
)
from app.core.utils import get_version
from app.core.celery_queue import CeleryJobManager

__all__ = [
    "API_KEY",
    "API_VERSION",
    "HOST",
    "PORT",
    "REDIS_URL",
    "MAX_WORKERS",
    "job_manager",
    "process_video_in_process",
    "shutdown_process_pool",
    "get_version",
    "CeleryJobManager",
]
