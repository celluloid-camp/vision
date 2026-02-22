"""Celery tasks for video processing"""
import json
import logging
import os
import time
import traceback
from datetime import datetime

import cv2
import requests

from app.core.celery_app import celery_app
from app.detection.detect_objects import ObjectDetector, download_video

logger = logging.getLogger(__name__)


def _send_callback_sync(job_id, external_id, callback_url, status, results=None, error=None):
    """Send callback notification synchronously with retry logic"""
    callback_data = {
        "job_id": job_id,
        "external_id": external_id,
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    if status == "completed" and results:
        callback_data["results"] = results
    elif status == "failed" and error:
        callback_data["error"] = error

    max_retries = 10
    retry_delay = 30

    for attempt in range(max_retries):
        try:
            response = requests.post(
                callback_url,
                json=callback_data,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if 200 <= response.status_code < 300:
                logger.info(f"Callback sent successfully to {callback_url} (attempt {attempt + 1})")
                return
            elif 400 <= response.status_code < 500 and response.status_code not in [408, 429]:
                logger.error(f"Client error {response.status_code}, not retrying")
                break
            else:
                logger.warning(f"Callback attempt {attempt + 1} returned {response.status_code}")
        except Exception as exc:
            logger.warning(f"Callback attempt {attempt + 1} failed: {exc}")

        if attempt < max_retries - 1:
            time.sleep(retry_delay)
            retry_delay *= 2

    logger.error(f"All callback attempts failed for job {job_id} to {callback_url}")


@celery_app.task(bind=True, name="app.core.tasks.process_video_task")
def process_video_task(self, job_data: dict):
    """Celery task for processing a video detection job"""
    job_id = job_data["job_id"]
    external_id = job_data["external_id"]
    video_url = job_data["video_url"]
    similarity_threshold = float(job_data["similarity_threshold"])
    callback_url = job_data.get("callback_url")
    start_time = datetime.now().isoformat()

    self.update_state(
        state="PROCESSING",
        meta={
            "job_id": job_id,
            "external_id": external_id,
            "video_url": video_url,
            "similarity_threshold": similarity_threshold,
            "callback_url": callback_url,
            "status": "processing",
            "progress": 0.0,
            "start_time": start_time,
        },
    )

    try:
        # Create output directory for this project
        output_dir = os.path.join("outputs", external_id)
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"detections_{job_id}_{timestamp}.json"
        output_path = os.path.join(output_dir, output_filename)

        # Download video if it's a URL
        if video_url.startswith(("http://", "https://")):
            video_path = download_video(video_url)
        else:
            video_path = video_url

        # Validate video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Video file not valid")
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count == 0:
            raise ValueError(f"Video contains no video stream. It may be audio-only: {video_path}")
        cap.release()

        # Process the video
        detector = ObjectDetector(
            min_score=0.8,
            output_path=output_path,
            similarity_threshold=similarity_threshold,
            external_id=external_id,
        )

        _last_reported = [0.0]

        def _report_progress(pct: float):
            # Report at most once per 5% increment to limit Redis writes
            if pct - _last_reported[0] >= 5.0 or pct >= 100.0:
                _last_reported[0] = pct
                self.update_state(
                    state="PROCESSING",
                    meta={
                        "job_id": job_id,
                        "external_id": external_id,
                        "status": "processing",
                        "progress": round(pct, 1),
                        "start_time": start_time,
                    },
                )

        results = detector.process_video(video_path, video_url, progress_callback=_report_progress)

        # Save results to disk
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Result file saved to: {output_path}")

        # Extract metadata
        processing = results["metadata"]["processing"]
        detection_stats = processing["detection_statistics"]
        metadata = {
            "frames_processed": processing["frames_processed"],
            "frames_with_detections": processing["frames_with_detections"],
            "total_detections": detection_stats["total_detections"],
            "processing_time": processing["duration_seconds"],
        }

        end_time = datetime.now().isoformat()

        logger.info(f"Job {job_id} completed successfully")

        # Send completion callback
        if callback_url:
            _send_callback_sync(job_id, external_id, callback_url, "completed", {"result_path": output_path, "metadata": metadata})

        # Clean up downloaded video
        if video_url.startswith(("http://", "https://")):
            try:
                os.remove(video_path)
                logger.info(f"Cleaned up temporary video file: {video_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary video file: {str(e)}")

        return {
            "job_id": job_id,
            "external_id": external_id,
            "video_url": video_url,
            "similarity_threshold": similarity_threshold,
            "callback_url": callback_url,
            "status": "completed",
            "result_path": output_path,
            "start_time": start_time,
            "end_time": end_time,
            "metadata": metadata,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed: {error_msg}")
        logger.error(traceback.format_exc())

        # Send failure callback
        if callback_url:
            _send_callback_sync(job_id, external_id, callback_url, "failed", error=error_msg)

        raise
