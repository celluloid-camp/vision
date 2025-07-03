import os
import json
import logging
from datetime import datetime, timedelta
import uuid
import asyncio
from typing import Annotated, Dict, Optional
import traceback
import aiohttp
import aiofiles
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from fastapi.security import APIKeyHeader
from scalar_fastapi import get_scalar_api_reference

# Import detection types
from detection_schemas import DetectionResults

# Import job types
from job import JobStatus

# Import Pydantic models
from result_models import (
    HealthResponse,
    AnalysisRequest,
    AnalysisResponse,
    JobStatusResponse,
    JobsListResponse,
    QueueStatusResponse,
    DeleteJobResponse,
    DetectionResultsModel,
)

# Import the object detection functionality from root directory
from detect_objects import ObjectDetector, download_video

from dotenv import load_dotenv

load_dotenv()
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_key = os.getenv("API_KEY")


# Import the RQ job manager
from rq_queue import RQJobManager

# Import persistent results index helpers
from results_index import update_result_index, get_result_from_index


# --- FastAPI integration ---
from fastapi import Depends, FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# Initialize RQ job manager
job_manager = RQJobManager()

# Process pool executor for CPU-intensive video processing
process_pool = ProcessPoolExecutor(
    max_workers=1
)  # Only 1 worker since we process one job at a time


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up FastAPI web service with RQ...")

    # Create output directory
    os.makedirs("outputs", exist_ok=True)

    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Test Redis connection
    try:
        job_manager.redis_conn.ping()
        logger.info(f"Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

    # Clean up stale jobs
    job_manager.cleanup_stale_jobs()

    # Start background job processor
    asyncio.create_task(process_rq_jobs())

    yield

    # Shutdown
    logger.info("Shutting down FastAPI web service...")
    process_pool.shutdown(wait=True)


# Create FastAPI app
app = FastAPI(
    title="Celluloid Video Analysis API",
    version="1.0.0",
    lifespan=lifespan,
    servers=[
        {
            "url": "https://analysis.celluloid.me",
            "description": "Production environment",
        },
    ],
)


header_scheme = APIKeyHeader(name="x-api-key")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the outputs directory as static files
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")


def process_video_in_process(
    video_path: str,
    video_url: str,
    output_path: str,
    similarity_threshold: float,
    project_id: str,
) -> DetectionResults:
    """Process video in a separate process (this function runs in the process pool)"""
    # Import here to avoid issues with multiprocessing
    from detect_objects import ObjectDetector

    # Initialize detector
    detector = ObjectDetector(
        min_score=0.8,  # Default confidence threshold
        output_path=output_path,
        similarity_threshold=similarity_threshold,
        project_id=project_id,
    )

    # Process the video
    results = detector.process_video(video_path, video_url)
    return results


async def process_video_job(job: JobStatus):
    """Process video job in the web service"""
    try:
        job.status = "processing"
        job.start_time = datetime.now()
        job_manager.save_job_to_rq(job)  # Save status update to RQ

        logger.info(f"Starting job {job.job_id} for project {job.project_id}")

        # Create output directory for this project
        output_dir = os.path.join("outputs", job.project_id)
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"detections_{job.job_id}_{timestamp}.json"
        output_path = os.path.join(output_dir, output_filename)

        # Download video if it's a URL
        if job.video_url.startswith(("http://", "https://")):
            video_path = download_video(job.video_url)
        else:
            video_path = job.video_url

        # Process the video in a separate process
        loop = asyncio.get_event_loop()
        results: DetectionResults = await loop.run_in_executor(
            process_pool,
            process_video_in_process,
            video_path,
            job.video_url,
            output_path,
            job.similarity_threshold,
            job.project_id,
        )

        # Save results
        async with aiofiles.open(output_path, "w") as f:
            await f.write(json.dumps(results, indent=2))

        job.status = "completed"
        job.end_time = datetime.now()
        job.result_path = output_path

        # Extract metadata directly from results
        processing = results["metadata"]["processing"]
        detection_stats = processing["detection_statistics"]
        job.metadata = {
            "frames_processed": processing["frames_processed"],
            "frames_with_detections": processing["frames_with_detections"],
            "total_detections": detection_stats["total_detections"],
            "processing_time": processing["duration_seconds"],
        }

        job_manager.save_job_to_rq(job)  # Save final status to RQ

        # Update persistent results index
        update_result_index(job.job_id, output_path, job.status, job.metadata)

        logger.info(f"Job {job.job_id} completed successfully")

        # Send completion callback
        await send_callback(job, "completed", results)

        # Clean up downloaded video if it was downloaded
        if job.video_url.startswith(("http://", "https://")):
            try:
                os.remove(video_path)
                logger.info(f"Cleaned up temporary video file: {video_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary video file: {str(e)}")

    except Exception as e:
        job.status = "failed"
        job.end_time = datetime.now()
        job.error_message = str(e)

        job_manager.save_job_to_rq(job)  # Save failure status to RQ

        logger.error(f"Job {job.job_id} failed: {str(e)}")
        logger.error(traceback.format_exc())

        # Send failure callback
        await send_callback(job, "failed", error=str(e))


async def process_rq_jobs():
    """Background task that processes RQ jobs"""
    while True:
        try:
            # Check if there are any jobs in the queue
            if len(job_manager.rq_queue) > 0:
                # Get the first job from the queue
                job_ids = job_manager.rq_queue.job_ids
                if job_ids:
                    job_id = job_ids[0]
                    rq_job = job_manager.rq_queue.fetch_job(job_id)

                    # Check if job is still queued (not being processed by another worker)
                    if rq_job and rq_job.is_queued:
                        # Get job metadata from RQ
                        job = job_manager.get_job_from_rq(job_id)
                        if job:
                            # Process the job
                            await process_video_job(job)
                            job_manager.delete_job(job_id)
                            logger.info(f"Processed and removed RQ job {job_id}")

            # Wait before checking again
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in RQ job processor: {str(e)}")
            logger.error(traceback.format_exc())
            await asyncio.sleep(5)  # Wait longer on error


async def send_callback(
    job: JobStatus, status: str, results: Dict = None, error: str = None
):
    """Send callback to the specified URL when job completes or fails"""
    if not job.callback_url:
        return

    try:
        callback_data = {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }

        if status == "completed":
            callback_data["results"] = {
                "result_path": job.result_path,
                "metadata": job.metadata,
            }
        elif status == "failed":
            callback_data["error"] = error or job.error_message

        # Simple headers without authentication
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MediaPipe-ObjectDetection-Service/1.0",
        }

        # Send POST request to callback URL with retry logic
        max_retries = 10
        retry_delay = 30  # seconds

        async with aiohttp.ClientSession() as session:
            for attempt in range(max_retries):
                try:
                    async with session.post(
                        job.callback_url,
                        json=callback_data,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if 200 <= response.status < 300:
                            logger.info(
                                f"Callback sent successfully to {job.callback_url} (attempt {attempt + 1})"
                            )
                            return
                        else:
                            logger.warning(
                                f"Callback failed with status {response.status}: {await response.text()} (attempt {attempt + 1})"
                            )

                            # Don't retry on client errors (4xx) except 408, 429
                            if (
                                400 <= response.status < 500
                                and response.status not in [408, 429]
                            ):
                                logger.error(
                                    f"Client error {response.status}, not retrying"
                                )
                                break

                except asyncio.TimeoutError:
                    logger.warning(f"Callback timeout on attempt {attempt + 1}")
                except aiohttp.ClientError as e:
                    logger.warning(
                        f"Callback connection error on attempt {attempt + 1}: {str(e)}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Callback request error on attempt {attempt + 1}: {str(e)}"
                    )

                # Wait before retry (except on last attempt)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

            # If all retries failed, log the final error
            logger.error(
                f"All callback attempts failed for job {job.job_id} to {job.callback_url}"
            )

    except Exception as e:
        logger.error(f"Failed to send callback to {job.callback_url}: {str(e)}")
        logger.error(traceback.format_exc())


@app.get("/health", response_model=HealthResponse)
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


@app.post(
    "/analyse",
    response_model=AnalysisResponse,
    status_code=202,
    summary="Analyse a video",
)
async def start_detection(
    body: AnalysisRequest, key: Annotated[str, Depends(header_scheme)]
):
    """Start video analysis on a video"""

    if key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

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


@app.get("/status/{job_id}", response_model=JobStatusResponse)
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


@app.get("/results/{job_id}", response_model=DetectionResultsModel)
async def get_job_results(job_id: str):
    """Get the results of a completed detection job"""
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
        return result_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading results for job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading results: {str(e)}")


@app.get("/jobs", response_model=JobsListResponse)
async def list_jobs(
    key: Annotated[str, Depends(header_scheme)],
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List all jobs with optional filtering"""

    if key != api_key:
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


@app.get("/queue", response_model=QueueStatusResponse)
async def get_queue_status(key: Annotated[str, Depends(header_scheme)]):
    """Get detailed queue status"""

    if key != api_key:
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


@app.get("/", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8081, reload=False, log_level="info")
