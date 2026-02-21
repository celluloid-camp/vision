"""Shared dependencies and services"""
from app.core.celery_queue import CeleryJobManager

# Initialize Celery job manager (singleton)
job_manager = CeleryJobManager()
