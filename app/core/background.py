"""Background task processing"""
import asyncio
import logging
from datetime import datetime
import os
import json
import traceback
import cv2
import aiohttp
import aiofiles
from concurrent.futures import ProcessPoolExecutor

from app.models.schemas import DetectionResults, JobStatus
from app.core.dependencies import job_manager
from detect_objects import download_video, ObjectDetector
from results_index import update_result_index

logger = logging.getLogger(__name__)

# Process pool executor for CPU-intensive video processing
process_pool = ProcessPoolExecutor(max_workers=1)


def process_video_in_process(
    video_path: str,
    video_url: str,
    output_path: str,
    similarity_threshold: float,
    project_id: str,
) -> DetectionResults:
    """Process video in a separate process (this function runs in the process pool)"""
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


async def send_callback(
    job: JobStatus, status: str, results: dict = None, error: str = None
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

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Video file not valid")
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count == 0:
            raise ValueError(
                f"Video contains no video stream (only audio?): {video_path}"
            )
        cap.release()

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

        logger.info(f"Result file saved to: {output_path}")
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

        # Update persistent results index with failed status and error info
        update_result_index(
            job.job_id, None, job.status, {"error_message": job.error_message}
        )

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


def shutdown_process_pool():
    """Shutdown the process pool"""
    process_pool.shutdown(wait=True)
