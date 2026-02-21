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
    status: str
    timestamp: str
    queue_size: int
    processing_jobs: int
    current_job: Optional[str]
    redis_connected: bool = False
    job_stats: Optional[JobStats] = None


class ErrorResponse(BaseModel):
    error: str


class AnalysisRequest(BaseModel):
    project_id: str = Field(..., description="Project identifier")
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
    callback_url: Optional[str]


class JobStatusResponse(BaseModel):
    job_id: str
    project_id: str
    video_url: str
    similarity_threshold: float
    status: str
    progress: float
    queue_position: Optional[int]
    estimated_wait_time: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    result_path: Optional[str]
    metadata: Optional[dict]
    error_message: Optional[str]


class JobInfo(BaseModel):
    job_id: str
    project_id: str
    status: str
    progress: float
    queue_position: Optional[int]
    start_time: Optional[str]
    end_time: Optional[str]


class JobsListResponse(BaseModel):
    jobs: list[JobInfo]
    total: int
    queue_size: int
    processing_jobs: int


class QueuedJob(BaseModel):
    job_id: str
    project_id: str
    queue_position: int
    estimated_wait_time: str


class CurrentJob(BaseModel):
    job_id: str
    project_id: str
    start_time: Optional[str]


class QueueStatusResponse(BaseModel):
    queue_size: int
    processing_jobs: int
    current_job: Optional[CurrentJob]
    queued_jobs: list[QueuedJob]


class DeleteJobResponse(BaseModel):
    message: str


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


class ModelMetadataModel(BaseModel):
    name: str
    type: str
    version: str


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
    model: ModelMetadataModel
    sprite: SpriteMetadataModel
    processing: ProcessingMetadataModel


class DetectionResultsModel(BaseModel):
    version: str
    metadata: ResultsMetadataModel
    frames: list[DetectionFrameModel]


# Pydantic models for path parameters
class JobIdPath(BaseModel):
    job_id: str = Field(..., description="job id")
