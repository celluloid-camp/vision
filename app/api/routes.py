"""API route handlers"""
import logging
import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app.core.config import API_KEY
from app.core.dependencies import job_manager
from app.models.result_models import (
    HealthResponse,
    AnalysisRequest,
    AnalysisResponse,
    JobStatusResponse,
    JobsListResponse,
    QueueStatusResponse,
    DetectionResultsModel,
)
from app.models.schemas import JobStatus
from results_index import get_result_from_index

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

        # Get queue status
        queue_status = job_manager.get_queue_status_info()

        # Count jobs by status using RQ
        all_jobs = job_manager.get_all_jobs_from_rq()
        queued_jobs = len([j for j in all_jobs if j.status == "queued"])
        processing_jobs = len([j for j in all_jobs if j.status == "processing"])
        completed_jobs = len([j for j in all_jobs if j.status == "completed"])
        failed_jobs = len([j for j in all_jobs if j.status == "failed"])

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "queue_size": queue_status["queue_length"],
            "processing_jobs": processing_jobs,
            "current_job": (
                queue_status["current_job"].id if queue_status["current_job"] else None
            ),
            "redis_connected": True,
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
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "redis_connected": False,
            "queue_size": 0,
            "processing_jobs": 0,
            "current_job": None,
            "job_stats": {"queued": 0, "processing": 0, "completed": 0, "failed": 0},
        }


@router.post(
    "/analyse",
    response_model=AnalysisResponse,
    status_code=202,
    summary="Analyse a video",
    tags=["analysis"],
)
async def start_detection(
    body: AnalysisRequest, key: Annotated[str, Depends(header_scheme)]
):
    """Start video analysis on a video"""

    if key != API_KEY:
        logger.error(f"Invalid API key: {key}")
        raise HTTPException(status_code=401, detail=f"Invalid API key: {key}    ")

    try:
        # Check if there's already a job for this project_id
        all_jobs = job_manager.get_all_jobs_from_rq()
        logger.info(f"Found {len(all_jobs)} total jobs in RQ")

        existing_jobs = [job for job in all_jobs if job.project_id == body.project_id]
        logger.info(f"Found {len(existing_jobs)} jobs for project {body.project_id}")

        # Check for active jobs (queued or processing)
        active_jobs = [
            job for job in existing_jobs if job.status in ["queued", "processing"]
        ]
        if active_jobs:
            # Return the existing job info
            existing_job = active_jobs[0]
            logger.info(
                f"Returning existing active job {existing_job.job_id} for project {body.project_id}"
            )
            return {
                "job_id": existing_job.job_id,
                "status": existing_job.status,
                "queue_position": 1,
                "message": f"Project {body.project_id} already has an active job",
                "callback_url": existing_job.callback_url,
                "rq_job_id": existing_job.job_id,
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
                f"Returning recently completed job {existing_job.job_id} for project {body.project_id}"
            )
            return {
                "job_id": existing_job.job_id,
                "status": existing_job.status,
                "queue_position": 0,
                "message": f"Project {body.project_id} was recently completed",
                "callback_url": existing_job.callback_url,
                "rq_job_id": existing_job.job_id,
            }

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create job status
        job = JobStatus(
            job_id,
            body.project_id,
            body.video_url,
            body.similarity_threshold,
            body.callback_url,
        )
        job.status = "queued"
        job.start_time = datetime.now()

        # Add job to RQ queue using the job manager
        rq_job = job_manager.enqueue_job(job)

        logger.info(f"Started detection job {job_id} for project {body.project_id}")
        if body.callback_url:
            logger.info(f"Callback URL configured: {body.callback_url}")

        return {
            "job_id": job_id,
            "status": "queued",
            "queue_position": 1,  # RQ doesn't provide position, assume 1
            "message": "Video analysis job added to queue",
            "callback_url": body.callback_url,
            "rq_job_id": rq_job.id,
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
        # Get job metadata from RQ
        job = job_manager.get_job_from_rq(job_id)
        job_info = None
        if not job:
            # Try persistent index
            job_info = get_result_from_index(job_id)
            if not job_info:
                raise HTTPException(status_code=404, detail="Job not found")
            # Compose a minimal JobStatusResponse from index with valid types
            return {
                "job_id": job_id,
                "project_id": "",
                "video_url": "",
                "similarity_threshold": 0.0,
                "status": job_info.get("status", "unknown"),
                "progress": 0.0,
                "queue_position": None,
                "estimated_wait_time": None,
                "start_time": None,
                "end_time": None,
                "result_path": job_info.get("result_path"),
                "metadata": job_info.get("metadata"),
                "error_message": None,
            }

        response = {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "video_url": job.video_url,
            "similarity_threshold": job.similarity_threshold,
            "status": job.status,
            "progress": job.progress,
            "queue_position": None,
            "estimated_wait_time": None,
            "start_time": job.start_time.isoformat() if job.start_time else None,
            "end_time": job.end_time.isoformat() if job.end_time else None,
            "result_path": job.result_path,
            "metadata": job.metadata,
            "error_message": job.error_message,
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting job status: {str(e)}"
        )


@router.get(
    "/results/{job_id}",
    response_model=DetectionResultsModel,
    summary="Get the results of a completed detection job",
    tags=["results"],
)
async def get_job_results(job_id: str):
    try:
        # Get job metadata from RQ
        job = job_manager.get_job_from_rq(job_id)
        result_data = None
        if not job:
            # Try persistent index
            result_data = get_result_from_index(job_id)
            if not result_data:
                raise HTTPException(status_code=404, detail="Job not found")
        else:
            raise HTTPException(status_code=500, detail="Job queued")
        if not result_data:
            raise HTTPException(
                status_code=404, detail="Result file not found or invalid"
            )
        if result_data.get("status") == "failed":
            return JSONResponse(
                status_code=400,
                content={
                    "job_id": job_id,
                    "status": "failed",
                    "error_message": result_data.get("metadata", {}).get(
                        "error_message", "Unknown error"
                    ),
                },
            )
        return result_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading results for job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading results: {str(e)}")


@router.get("/jobs", response_model=JobsListResponse, include_in_schema=False)
async def list_jobs(
    key: Annotated[str, Depends(header_scheme)],
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List all jobs with optional filtering"""

    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        filtered_jobs = job_manager.get_all_jobs_from_rq()

        if project_id:
            filtered_jobs = [j for j in filtered_jobs if j.project_id == project_id]

        if status:
            filtered_jobs = [j for j in filtered_jobs if j.status == status]

        job_list = []
        for job in filtered_jobs:
            job_info = {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "status": job.status,
                "progress": job.progress,
                "queue_position": getattr(job, "queue_position", None),
                "start_time": (
                    job.start_time.isoformat()
                    if getattr(job, "start_time", None)
                    else None
                ),
                "end_time": (
                    job.end_time.isoformat() if getattr(job, "end_time", None) else None
                ),
            }
            job_list.append(job_info)

        # Sort by start time
        job_list.sort(key=lambda x: x.get("start_time", ""))

        # Get queue status
        queue_status = job_manager.get_queue_status_info()

        return {
            "jobs": job_list,
            "total": len(job_list),
            "queue_size": queue_status["queue_length"],
            "processing_jobs": len(
                [j for j in filtered_jobs if j.status == "processing"]
            ),
        }

    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing jobs: {str(e)}")


@router.get("/queue", response_model=QueueStatusResponse, include_in_schema=False)
async def get_queue_status(key: Annotated[str, Depends(header_scheme)]):
    """Get detailed queue status"""

    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        queue_status = job_manager.get_queue_status_info()

        # Get queued jobs
        queued_jobs = job_manager.get_queued_jobs()

        # Get current job info
        current_job_info = None
        if queue_status["current_job"]:
            current_job = queue_status["current_job"]
            job_meta = job_manager.get_job_from_rq(current_job.id)

            current_job_info = {
                "job_id": current_job.id,
                "project_id": job_meta.project_id if job_meta else "unknown",
                "start_time": (
                    current_job.started_at.isoformat()
                    if current_job.started_at
                    else None
                ),
            }

        return {
            "queue_size": queue_status["queue_length"],
            "processing_jobs": 1 if queue_status["current_job"] else 0,
            "current_job": current_job_info,
            "queued_jobs": queued_jobs,
            "failed_jobs": queue_status["failed_count"],
        }

    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting queue status: {str(e)}"
        )
