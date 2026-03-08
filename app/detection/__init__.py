"""Detection and scene analysis modules"""

from app.core.utils import download_video
from app.detection.object_detect import ObjectDetector
from app.detection.scene_detect import detect_scenes_from_file as detect_scenes

__all__ = ["ObjectDetector", "download_video", "detect_scenes"]
