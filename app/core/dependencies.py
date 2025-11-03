"""Shared dependencies and services"""
from rq_queue import RQJobManager

# Initialize RQ job manager (singleton)
job_manager = RQJobManager()
