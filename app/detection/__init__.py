"""Detection and scene analysis modules"""

from app.core.utils import download_video
from app.detection.detect_objects import ObjectDetector
from app.detection.scenes import detect_scenes_from_file as detect_scenes

__all__ = ["ObjectDetector", "download_video", "detect_scenes"]
