from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from datetime import datetime


# --- Type definitions for detection results ---
class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DetectionObject(BaseModel):
    id: str
    class_name: str
    confidence: float
    bbox: BoundingBox
    thumbnail: str


class DetectionFrame(BaseModel):
    frame_idx: int
    timestamp: float
    objects: List[DetectionObject]


class VideoMetadata(BaseModel):
    fps: float
    frame_count: int
    width: int
    height: int
    source: str


class ModelMetadata(BaseModel):
    name: str
    type: str
    version: str


class SpriteMetadata(BaseModel):
    path: str
    thumbnail_size: List[int]


class DetectionStatistics(BaseModel):
    total_detections: int
    person_detections: int
    person_with_face: int
    person_without_face: int
    other_detections: int
    class_counts: Dict[str, int]


class ProcessingMetadata(BaseModel):
    start_time: str
    end_time: str
    duration_seconds: float
    frames_processed: int
    frames_with_detections: int
    processing_speed: float
    detection_statistics: DetectionStatistics


class ResultsMetadata(BaseModel):
    video: VideoMetadata
    model: ModelMetadata
    sprite: SpriteMetadata
    processing: ProcessingMetadata


class DetectionResults(BaseModel):
    version: str
    metadata: ResultsMetadata
    frames: List[DetectionFrame]


class JobStatus:
    def __init__(
        self,
        job_id: str,
        project_id: str,
        video_url: str,
        similarity_threshold: float,
        callback_url: str = None,
    ):
        self.job_id = job_id
        self.project_id = project_id
        self.video_url = video_url
        self.similarity_threshold = similarity_threshold
        self.callback_url = callback_url
        self.status = "queued"  # queued, processing, completed, failed
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.progress = 0.0
        self.result_path: Optional[str] = None
        self.error_message: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self.queue_position = 0
