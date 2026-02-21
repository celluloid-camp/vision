"""Celery-based job manager (replaces RQ-based job manager)"""
import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import redis
from celery.result import AsyncResult

from app.core.celery_app import CELERY_QUEUE_NAME, CELERY_TASK_TIMEOUT, celery_app
from app.models.schemas import JobStatus

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is required but not set")

JOB_KEY_PREFIX = "celluloid:job:"
JOB_REGISTRY_KEY = "celluloid:jobs"


ESTIMATED_MINUTES_PER_JOB = 5


class CeleryJobManager:
    def __init__(self, redis_url: str = REDIS_URL, queue_name: str = CELERY_QUEUE_NAME):
        """Initialize Celery job manager"""
        self.redis_url = redis_url
        self.queue_name = queue_name

        # Redis connection for job metadata storage
        self.redis_conn = redis.from_url(redis_url)

        logger.info(f"Initialized Celery job manager with queue: {queue_name}")

    def _job_key(self, job_id: str) -> str:
        return f"{JOB_KEY_PREFIX}{job_id}"

    def _save_job_meta(self, job: JobStatus):
        """Persist job metadata in Redis"""
        data = {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "video_url": job.video_url,
            "similarity_threshold": float(job.similarity_threshold),
            "callback_url": job.callback_url,
            "status": job.status,
            "progress": float(job.progress),
            "result_path": job.result_path,
            "error_message": job.error_message,
            "metadata": job.metadata,
            "start_time": job.start_time.isoformat() if job.start_time else None,
            "end_time": job.end_time.isoformat() if job.end_time else None,
        }
        self.redis_conn.setex(self._job_key(job.job_id), 86400, json.dumps(data))
        self.redis_conn.sadd(JOB_REGISTRY_KEY, job.job_id)

    def _load_job_meta(self, job_id: str) -> Optional[dict]:
        """Load job metadata from Redis"""
        raw = self.redis_conn.get(self._job_key(job_id))
        if raw:
            return json.loads(raw)
        return None

    def get_job_from_celery(self, job_id: str) -> Optional[JobStatus]:
        """Get job status from Celery task state and Redis metadata"""
        try:
            meta = self._load_job_meta(job_id)
            if not meta:
                return None

            job = JobStatus(
                job_id=job_id,
                project_id=meta.get("project_id", "unknown"),
                video_url=meta.get("video_url", "unknown"),
                similarity_threshold=float(meta.get("similarity_threshold", 0.0)),
                callback_url=meta.get("callback_url"),
            )

            # Determine status from Celery task state
            result = AsyncResult(job_id, app=celery_app)
            celery_state = result.state

            if celery_state == "PENDING":
                job.status = "queued"
            elif celery_state in ("STARTED", "PROCESSING"):
                job.status = "processing"
            elif celery_state == "SUCCESS":
                job.status = "completed"
            elif celery_state in ("FAILURE", "REVOKED"):
                job.status = "failed"
            else:
                job.status = meta.get("status", "queued")

            job.progress = float(meta.get("progress", 0.0))
            job.result_path = meta.get("result_path")
            job.error_message = meta.get("error_message")
            job.metadata = meta.get("metadata", {})

            if meta.get("start_time"):
                job.start_time = datetime.fromisoformat(meta["start_time"])
            if meta.get("end_time"):
                job.end_time = datetime.fromisoformat(meta["end_time"])

            return job
        except Exception as e:
            logger.error(f"Error getting job {job_id} from Celery: {str(e)}")
            return None

    def save_job_to_celery(self, job: JobStatus):
        """Save job status to Redis metadata"""
        try:
            self._save_job_meta(job)
        except Exception as e:
            logger.error(f"Error saving job {job.job_id} to Celery: {str(e)}")

    def get_all_jobs(self) -> List[JobStatus]:
        """Get all tracked jobs from the job registry"""
        jobs = []
        try:
            job_ids = self.redis_conn.smembers(JOB_REGISTRY_KEY)
            for job_id_bytes in job_ids:
                job_id = job_id_bytes.decode("utf-8") if isinstance(job_id_bytes, bytes) else job_id_bytes
                job = self.get_job_from_celery(job_id)
                if job:
                    jobs.append(job)
        except Exception as e:
            logger.error(f"Error getting all jobs: {str(e)}")
        return jobs

    def cleanup_stale_jobs(self):
        """Remove job registry entries whose metadata has expired"""
        try:
            logger.info("Cleaning up stale job references...")
            job_ids = self.redis_conn.smembers(JOB_REGISTRY_KEY)
            for job_id_bytes in job_ids:
                job_id = job_id_bytes.decode("utf-8") if isinstance(job_id_bytes, bytes) else job_id_bytes
                if not self._load_job_meta(job_id):
                    self.redis_conn.srem(JOB_REGISTRY_KEY, job_id)
                    logger.info(f"Removed stale job {job_id} from registry")
            logger.info("Stale job cleanup completed")
        except Exception as e:
            logger.error(f"Error cleaning up stale jobs: {str(e)}")

    def get_queue_status_info(self):
        """Get current queue status from Celery"""
        try:
            inspector = celery_app.control.inspect(timeout=1.0)
            active = inspector.active() or {}
            reserved = inspector.reserved() or {}

            active_tasks = [t for tasks in active.values() for t in tasks]
            queued_tasks = [t for tasks in reserved.values() for t in tasks]

            current_job_id = active_tasks[0]["id"] if active_tasks else None
            queue_length = len(queued_tasks)

            return {
                "queue_length": queue_length,
                "current_job": current_job_id,
                "failed_count": 0,
                "finished_count": 0,
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {
                "queue_length": 0,
                "current_job": None,
                "failed_count": 0,
                "finished_count": 0,
            }

    def enqueue_job(self, job: JobStatus, job_timeout: int = CELERY_TASK_TIMEOUT, result_ttl: int = 86400):
        """Enqueue a job to the Celery queue"""
        try:
            from app.core.tasks import process_video_task

            job_data = {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "video_url": job.video_url,
                "similarity_threshold": job.similarity_threshold,
                "callback_url": job.callback_url,
            }

            result = process_video_task.apply_async(
                args=[job_data],
                task_id=job.job_id,
                queue=self.queue_name,
                soft_time_limit=job_timeout,
                time_limit=job_timeout + 60,
            )

            # Persist job metadata so it can be queried before the task starts
            self._save_job_meta(job)

            logger.info(f"Enqueued job {job.job_id} to Celery queue {self.queue_name}")
            return result
        except Exception as e:
            logger.error(f"Error enqueueing job {job.job_id}: {str(e)}")
            raise

    def delete_job(self, job_id: str):
        """Delete a job from Celery and Redis"""
        try:
            result = AsyncResult(job_id, app=celery_app)
            result.forget()
            self.redis_conn.delete(self._job_key(job_id))
            self.redis_conn.srem(JOB_REGISTRY_KEY, job_id)
            logger.info(f"Deleted job {job_id}")
        except Exception as e:
            logger.warning(f"Could not delete job {job_id}: {str(e)}")

    def cancel_job(self, job_id: str):
        """Cancel a queued or running job"""
        try:
            result = AsyncResult(job_id, app=celery_app)
            result.revoke(terminate=True)
            logger.info(f"Cancelled job {job_id}")
        except Exception as e:
            logger.warning(f"Could not cancel job {job_id}: {str(e)}")

    def get_queued_jobs(self):
        """Get list of queued jobs with metadata"""
        queued_jobs = []
        try:
            jobs = self.get_all_jobs()
            queued = [j for j in jobs if j.status == "queued"]
            for i, job in enumerate(queued):
                queued_jobs.append(
                    {
                        "job_id": job.job_id,
                        "project_id": job.project_id,
                        "queue_position": i + 1,
                        "estimated_wait_time": f"~{(i + 1) * ESTIMATED_MINUTES_PER_JOB} minutes",
                    }
                )
        except Exception as e:
            logger.error(f"Error getting queued jobs: {str(e)}")
        return queued_jobs

    def clean_queue(self):
        """Purge all pending tasks from the Celery queue"""
        try:
            celery_app.control.purge()
            logger.info("Celery queue cleaned.")
        except Exception as e:
            logger.error(f"Error cleaning Celery queue: {str(e)}")
