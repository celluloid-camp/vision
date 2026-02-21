"""Background task utilities (video processing is handled by Celery workers)"""
import logging
from concurrent.futures import ProcessPoolExecutor

from app.models.schemas import DetectionResults
from app.detection.detect_objects import ObjectDetector

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
    detector = ObjectDetector(
        min_score=0.8,
        output_path=output_path,
        similarity_threshold=similarity_threshold,
        project_id=project_id,
    )
    results = detector.process_video(video_path, video_url)
    return results


def shutdown_process_pool():
    """Shutdown the process pool"""
    process_pool.shutdown(wait=True)
