"""Core application logic and configuration"""
from app.core.config import API_KEY, API_VERSION, HOST, PORT, REDIS_URL, MAX_WORKERS
from app.core.dependencies import job_manager
from app.core.background import (
    process_rq_jobs,
    process_video_job,
    send_callback,
    shutdown_process_pool,
)

__all__ = [
    "API_KEY",
    "API_VERSION",
    "HOST",
    "PORT",
    "REDIS_URL",
    "MAX_WORKERS",
    "job_manager",
    "process_rq_jobs",
    "process_video_job",
    "send_callback",
    "shutdown_process_pool",
]
