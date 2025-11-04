"""Shared dependencies and services"""
from app.core.rq_queue import RQJobManager

# Initialize RQ job manager (singleton)
job_manager = RQJobManager()
