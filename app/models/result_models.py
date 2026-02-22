from pydantic import BaseModel, Field, field_validator
from typing import Optional
from urllib.parse import urlparse
import os


class JobStats(BaseModel):
    queued: int
    processing: int
    completed: int
    failed: int


# --- Pydantic models for OpenAPI ---
class HealthResponse(BaseModel):
    version: str
    status: str
    timestamp: str
    job_stats: Optional[JobStats] = None
    error: Optional[str] = None


class AnalysisRequest(BaseModel):
    external_id: str = Field(..., description="Project identifier")
    video_url: str = Field(..., description="URL or path to video file")
    similarity_threshold: float = Field(
        0.5, ge=0, le=1, description="Similarity threshold for object tracking"
    )
    callback_url: Optional[str] = Field(
        None, description="Callback URL for job completion notifications"
    )

    @field_validator("video_url")
    @classmethod
    def validate_video_url(cls, v):
        result = urlparse(v)
        if (result.scheme in ("http", "https") and result.netloc) or os.path.exists(v):
            return v
        raise ValueError("video_url must be a valid URL or an existing file path")


class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    queue_position: int
    message: str
    callback_url: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    external_id: str
    status: str
    progress: float
    queue_position: int = 0
    estimated_wait_time: str = "00:00:00"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error_message: Optional[str] = None


# Pydantic models for OpenAPI schema (matching TypedDict structure)
class BoundingBoxModel(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DetectionObjectModel(BaseModel):
    id: str
    class_name: str
    confidence: float
    bbox: BoundingBoxModel
    thumbnail: str


class DetectionFrameModel(BaseModel):
    frame_idx: int
    timestamp: float
    objects: list[DetectionObjectModel]


class VideoMetadataModel(BaseModel):
    fps: float
    frame_count: int
    width: int
    height: int
    source: str


class SpriteMetadataModel(BaseModel):
    path: str
    thumbnail_size: list[int]


class DetectionStatisticsModel(BaseModel):
    total_detections: Optional[int] = None
    person_detections: Optional[int] = None
    person_with_face: Optional[int] = None
    person_without_face: Optional[int] = None
    other_detections: Optional[int] = None
    class_counts: Optional[dict[str, int]] = None


class ProcessingMetadataModel(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    frames_processed: Optional[int] = None
    frames_with_detections: Optional[int] = None
    processing_speed: Optional[float] = None
    detection_statistics: Optional[DetectionStatisticsModel] = None


class ResultsMetadataModel(BaseModel):
    video: VideoMetadataModel
    sprite: SpriteMetadataModel
    processing: ProcessingMetadataModel


class DetectionResultsModel(BaseModel):
    version: str
    metadata: ResultsMetadataModel
    frames: list[DetectionFrameModel]


class JobResultsResponse(BaseModel):
    status: str
    data: Optional[DetectionResultsModel] = None
    error_message: Optional[str] = None
