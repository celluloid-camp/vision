import logging
from datetime import datetime, timedelta
import os
from typing import Optional, List
import redis
from rq import Queue, Worker
from rq.job import Job
from rq.registry import FailedJobRegistry, FinishedJobRegistry

from job import JobStatus

# Set up logging
logger = logging.getLogger(__name__)

# Redis and RQ configuration from environment variables
REDIS_URL = os.getenv('REDIS_URL')
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is required but not set")

RQ_QUEUE_NAME = os.getenv('RQ_QUEUE_NAME', 'celluloid_video_processing')
RQ_JOB_TIMEOUT = int(os.getenv('RQ_JOB_TIMEOUT', 3600))

class RQJobManager:
    def __init__(self, redis_url: str = REDIS_URL, queue_name: str = RQ_QUEUE_NAME):

        """Initialize RQ job manager"""
        self.redis_url = redis_url
        self.queue_name = queue_name

        # Initialize Redis connection
        self.redis_conn = redis.from_url(redis_url)

        # Initialize RQ queue
        self.rq_queue = Queue(queue_name, connection=self.redis_conn)

        logger.info(f"Initialized RQ job manager with queue: {queue_name}")

    def get_job_from_rq(self, job_id: str) -> Optional[JobStatus]:
        """Get job status from RQ job metadata"""
        try:
            rq_job = Job.fetch(job_id, connection=self.redis_conn)
            if not rq_job:
                return None

            # Extract job metadata from RQ job
            meta = rq_job.meta or {}

            # Helper function to safely decode strings
            def safe_decode(value):
                if isinstance(value, bytes):
                    try:
                        return value.decode("utf-8")
                    except UnicodeDecodeError:
                        return str(value)
                return value

            job = JobStatus(
                job_id=job_id,
                project_id=safe_decode(meta.get("project_id", "unknown")),
                video_url=safe_decode(meta.get("video_url", "unknown")),
                similarity_threshold=float(meta.get("similarity_threshold", 0.0)),
                callback_url=safe_decode(meta.get("callback_url")),
            )

            # Set status based on RQ job status
            if rq_job.is_queued:
                job.status = "queued"
            elif rq_job.is_started:
                job.status = "processing"
            elif rq_job.is_finished:
                job.status = "completed"
            elif rq_job.is_failed:
                job.status = "failed"

            # Set timestamps
            if rq_job.started_at:
                job.start_time = rq_job.started_at
            if rq_job.ended_at:
                job.end_time = rq_job.ended_at

            # Set additional metadata
            job.result_path = safe_decode(meta.get("result_path"))
            job.error_message = safe_decode(meta.get("error_message"))
            job.metadata = meta.get("metadata", {})
            job.progress = float(meta.get("progress", 0.0))

            return job
        except Exception as e:
            logger.error(f"Error getting job {job_id} from RQ: {str(e)}")
            return None

    def save_job_to_rq(self, job: JobStatus):
        """Save job status to RQ job metadata"""
        try:
            rq_job = Job.fetch(job.job_id, connection=self.redis_conn)
            if not rq_job:
                return

            # Update RQ job metadata
            meta = rq_job.meta or {}
            meta.update(
                {
                    "project_id": str(job.project_id),
                    "video_url": str(job.video_url),
                    "similarity_threshold": float(job.similarity_threshold),
                    "callback_url": str(job.callback_url) if job.callback_url else None,
                    "status": str(job.status),
                    "result_path": str(job.result_path) if job.result_path else None,
                    "error_message": (
                        str(job.error_message) if job.error_message else None
                    ),
                    "metadata": job.metadata,
                    "progress": float(job.progress),
                }
            )

            rq_job.meta = meta
            rq_job.save()

        except Exception as e:
            logger.error(f"Error saving job {job.job_id} to RQ: {str(e)}")

    def get_all_jobs_from_rq(self) -> List[JobStatus]:
        """Get all jobs from RQ (queued, started, finished, failed)"""
        jobs = []

        try:
            # Get queued jobs
            for job_id in self.rq_queue.job_ids:
                job = self.get_job_from_rq(job_id)
                if job:
                    jobs.append(job)
                else:
                    logger.warning(
                        f"Job {job_id} found in queue but could not be retrieved"
                    )

            # Get started jobs
            started_registry = self.rq_queue.started_job_registry
            for job_id in started_registry.get_job_ids():
                job = self.get_job_from_rq(job_id)
                if job:
                    jobs.append(job)
                else:
                    logger.warning(
                        f"Job {job_id} found in started registry but could not be retrieved"
                    )

            # Get finished jobs
            finished_registry = self.rq_queue.finished_job_registry
            for job_id in finished_registry.get_job_ids():
                job = self.get_job_from_rq(job_id)
                if job:
                    jobs.append(job)
                else:
                    logger.warning(
                        f"Job {job_id} found in finished registry but could not be retrieved"
                    )

            # Get failed jobs
            failed_registry = self.rq_queue.failed_job_registry
            for job_id in failed_registry.get_job_ids():
                job = self.get_job_from_rq(job_id)
                if job:
                    jobs.append(job)
                else:
                    logger.warning(
                        f"Job {job_id} found in failed registry but could not be retrieved"
                    )

        except Exception as e:
            logger.error(f"Error getting all jobs from RQ: {str(e)}")

        return jobs

    def cleanup_stale_jobs(self):
        """Clean up stale job references from RQ registries"""
        try:
            logger.info("Cleaning up stale job references...")

            # Clean up started registry
            started_registry = self.rq_queue.started_job_registry
            for job_id in started_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=self.redis_conn)
                    if not job or not job.exists:
                        started_registry.remove(job_id)
                        logger.info(f"Removed stale job {job_id} from started registry")
                except Exception as e:
                    started_registry.remove(job_id)
                    logger.info(
                        f"Removed invalid job {job_id} from started registry: {str(e)}"
                    )

            # Clean up finished registry - only remove jobs older than 1 day
            finished_registry = self.rq_queue.finished_job_registry
            one_day_ago = datetime.now() - timedelta(days=1)
            for job_id in finished_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=self.redis_conn)
                    if not job or not job.exists:
                        finished_registry.remove(job_id)
                        logger.info(
                            f"Removed stale job {job_id} from finished registry"
                        )
                    elif job.ended_at and job.ended_at < one_day_ago:
                        finished_registry.remove(job_id)
                        logger.info(
                            f"Removed old finished job {job_id} from finished registry (completed: {job.ended_at})"
                        )
                except Exception as e:
                    finished_registry.remove(job_id)
                    logger.info(
                        f"Removed invalid job {job_id} from finished registry: {str(e)}"
                    )

            # Clean up failed registry
            failed_registry = self.rq_queue.failed_job_registry
            for job_id in failed_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=self.redis_conn)
                    if not job or not job.exists:
                        failed_registry.remove(job_id)
                        logger.info(f"Removed stale job {job_id} from failed registry")
                except Exception as e:
                    failed_registry.remove(job_id)
                    logger.info(
                        f"Removed invalid job {job_id} from failed registry: {str(e)}"
                    )

            logger.info("Stale job cleanup completed")

        except Exception as e:
            logger.error(f"Error cleaning up stale jobs: {str(e)}")

    def get_queue_status_info(self):
        """Get current queue status from RQ"""
        try:
            # Get queue length
            queue_length = len(self.rq_queue)

            # Get current job (first job in queue)
            current_job = None
            if queue_length > 0:
                job_ids = self.rq_queue.job_ids
                if job_ids:
                    current_job_id = job_ids[0]
                    current_job = Job.fetch(current_job_id, connection=self.redis_conn)

            # Get failed jobs count
            failed_registry = FailedJobRegistry(queue=self.rq_queue)
            failed_count = len(failed_registry)

            # Get finished jobs count
            finished_registry = FinishedJobRegistry(queue=self.rq_queue)
            finished_count = len(finished_registry)

            return {
                "queue_length": queue_length,
                "current_job": current_job,
                "failed_count": failed_count,
                "finished_count": finished_count,
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {
                "queue_length": 0,
                "current_job": None,
                "failed_count": 0,
                "finished_count": 0,
            }

    def enqueue_job(
        self, job: JobStatus, job_timeout: int = RQ_JOB_TIMEOUT, result_ttl: int = 86400
    ):
        """Enqueue a job to RQ"""
        try:
            rq_job = self.rq_queue.enqueue(
                lambda: None,  # Dummy function, actual processing happens in web service
                job_timeout=job_timeout,
                result_ttl=result_ttl,  # Keep results for 24 hours
                job_id=job.job_id,
            )

            # Save job metadata to RQ
            self.save_job_to_rq(job)

            return rq_job
        except Exception as e:
            logger.error(f"Error enqueueing job {job.job_id}: {str(e)}")
            raise

    def delete_job(self, job_id: str):
        """Delete a job from RQ"""
        try:
            rq_job = Job.fetch(job_id, connection=self.redis_conn)
            if rq_job:
                rq_job.delete()
                logger.info(f"Deleted job {job_id} from RQ")
        except Exception as e:
            logger.warning(f"Could not delete RQ job {job_id}: {str(e)}")

    def cancel_job(self, job_id: str):
        """Cancel a queued job"""
        try:
            rq_job = Job.fetch(job_id, connection=self.redis_conn)
            if rq_job and rq_job.is_queued:
                rq_job.cancel()
                logger.info(f"Cancelled job {job_id}")
        except Exception as e:
            logger.warning(f"Could not cancel RQ job {job_id}: {str(e)}")

    def get_queued_jobs(self):
        """Get list of queued jobs with metadata"""
        queued_jobs = []
        try:
            job_ids = self.rq_queue.job_ids
            for i, job_id in enumerate(job_ids):
                job_meta = self.get_job_from_rq(job_id)
                if job_meta:
                    queued_jobs.append(
                        {
                            "job_id": job_id,
                            "project_id": job_meta.project_id,
                            "queue_position": i + 1,
                            "estimated_wait_time": f"~{(i + 1) * 5} minutes",
                        }
                    )
        except Exception as e:
            logger.error(f"Error getting queued jobs: {str(e)}")

        return queued_jobs

    def clean_queue(self):
        """Remove all jobs from the RQ queue (does not affect finished or failed registries)."""
        try:
            job_ids = self.rq_queue.job_ids
            for job_id in job_ids:
                self.rq_queue.remove(job_id)
                logger.info(f"Removed job {job_id} from RQ queue")
            logger.info("RQ queue cleaned.")
        except Exception as e:
            logger.error(f"Error cleaning RQ queue: {str(e)}")
