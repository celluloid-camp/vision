"""API route handlers"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import APIKeyHeader
from app.core.utils import get_version
from app.core.config import API_KEY
from app.core.dependencies import job_manager
from app.models.result_models import (
    HealthResponse,
    AnalysisRequest,
    AnalysisResponse,
    JobStatusResponse,
    JobResultsResponse,
)
from app.models.schemas import JobStatus

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter()

# API Key authentication
header_scheme = APIKeyHeader(name="x-api-key")


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint"""
    try:
        # Test Redis connection
        job_manager.redis_conn.ping()

        # Count jobs by status
        all_jobs = job_manager.get_all_jobs()
        queued_jobs = len([j for j in all_jobs if j.status == "queued"])
        processing_jobs = len([j for j in all_jobs if j.status == "processing"])
        completed_jobs = len([j for j in all_jobs if j.status == "completed"])
        failed_jobs = len([j for j in all_jobs if j.status == "failed"])

        return {
            "version": get_version(),
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "job_stats": {
                "queued": queued_jobs,
                "processing": processing_jobs,
                "completed": completed_jobs,
                "failed": failed_jobs,
            },
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "version": get_version(),
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": "Health check failed",
            "job_stats": {"queued": 0, "processing": 0, "completed": 0, "failed": 0},
        }


@router.post(
    "/job/analyse",
    response_model=AnalysisResponse,
    status_code=202,
    summary="Create an analysis task for a video",
    tags=["analysis"],
)
async def create_analysis_task(
    body: AnalysisRequest, key: Annotated[str, Depends(header_scheme)]
):
    """Start video analysis on a video"""

    if key != API_KEY:
        logger.error(f"Invalid API key: {key}")
        raise HTTPException(status_code=401, detail=f"Invalid API key: {key}")

    try:
        # Check if there's already a job for this external_id
        all_jobs = job_manager.get_all_jobs()
        logger.info(f"Found {len(all_jobs)} total jobs in Celery")

        existing_jobs = [job for job in all_jobs if job.external_id == body.external_id]
        logger.info(f"Found {len(existing_jobs)} jobs for project {body.external_id}")

        # Check for active jobs (queued or processing)
        active_jobs = [
            job for job in existing_jobs if job.status in ["queued", "processing"]
        ]
        if active_jobs:
            # Return the existing job info
            existing_job = active_jobs[0]
            logger.info(
                f"Returning existing active job {existing_job.job_id} for project {body.external_id}"
            )
            return {
                "job_id": existing_job.job_id,
                "status": existing_job.status,
                "queue_position": 1,
                "message": f"Project {body.external_id} already has an active job",
                "callback_url": existing_job.callback_url,
            }

        # Check for recently completed jobs (within last hour)
        recent_completed = [
            job
            for job in existing_jobs
            if job.status == "completed"
            and job.end_time
            and (datetime.now() - job.end_time).total_seconds() < 3600
        ]
        if recent_completed:
            existing_job = recent_completed[0]
            logger.info(
                f"Returning recently completed job {existing_job.job_id} for project {body.external_id}"
            )
            return {
                "job_id": existing_job.job_id,
                "status": existing_job.status,
                "queue_position": 0,
                "message": f"Project {body.external_id} was recently completed",
                "callback_url": existing_job.callback_url,
            }

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create job status
        job = JobStatus(
            job_id,
            body.external_id,
            body.video_url,
            body.similarity_threshold,
            body.callback_url,
        )
        job.status = "queued"
        job.start_time = datetime.now()

        # Add job to Celery queue using the job manager
        celery_result = job_manager.enqueue_job(job)  # noqa: F841

        logger.info(f"Started detection job {job_id} for project {body.external_id}")
        if body.callback_url:
            logger.info(f"Callback URL configured: {body.callback_url}")

        return {
            "job_id": job_id,
            "status": "queued",
            "queue_position": 1,
            "message": "Video analysis job added to queue",
            "callback_url": body.callback_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting detection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get the status of a detection job",
    tags=["status"],
)
async def get_job_status(job_id: str):
    """Get the status of a detection job"""
    try:
        job = job_manager.get_job_from_celery(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        queue_position = 0
        estimated_wait_time = "00:00:00"

        if job.status == "queued":
            queued = job_manager.get_queued_jobs()
            match = next((q for q in queued if q["job_id"] == job_id), None)
            if match:
                queue_position = match["queue_position"]
                estimated_wait_time = match["estimated_wait_time"]

        return {
            "job_id": job.job_id,
            "external_id": job.external_id,
            "status": job.status,
            "progress": job.progress,
            "queue_position": queue_position,
            "estimated_wait_time": estimated_wait_time,
            "start_time": job.start_time.isoformat() if job.start_time else None,
            "end_time": job.end_time.isoformat() if job.end_time else None,
            "error_message": job.error_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting job status: {str(e)}"
        )


@router.get(
    "/job/{job_id}/results",
    response_model=JobResultsResponse,
    summary="Get the results of a completed analysis job",
    tags=["results"],
)
async def get_job_results(job_id: str):
    try:
        job = job_manager.get_job_from_celery(job_id)
        if not job:
            return {"status": "not-found", "data": None}

        if job.status == "failed":
            return {
                "status": "failed",
                "data": None,
                "error_message": job.error_message or "Unknown error",
            }

        if job.status in ("queued", "processing"):
            return {"status": job.status, "data": None}

        # completed — load result file
        if not job.result_path or not os.path.exists(job.result_path):
            return {"status": "not-found", "data": None}

        with open(job.result_path) as f:
            result_data = json.load(f)

        return {"status": "completed", "data": result_data}

    except Exception as e:
        logger.error(f"Error reading results for job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading results: {str(e)}")
