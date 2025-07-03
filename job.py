from datetime import datetime
from typing import Optional, Dict, Any


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
