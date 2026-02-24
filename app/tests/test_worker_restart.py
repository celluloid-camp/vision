"""Unit tests for worker-restart / stuck-job detection in CeleryJobManager."""

import json
from unittest.mock import MagicMock, patch, PropertyMock

from app.core.celery_queue import CeleryJobManager


def _make_manager(mock_redis: MagicMock):
    """Return a CeleryJobManager whose Redis client is fully mocked."""
    manager = CeleryJobManager.__new__(CeleryJobManager)
    manager.queue_name = "test-queue"
    # Override the _client property at the instance level
    type(manager)._client = PropertyMock(return_value=mock_redis)
    return manager


def _redis_meta(status: str, error_message: str | None = None) -> dict:
    return {
        "job_id": "test-job-id",
        "external_id": "proj-1",
        "video_url": "http://example.com/v.mp4",
        "similarity_threshold": 0.5,
        "callback_url": None,
        "status": status,
        "progress": 42.0,
        "result_path": None,
        "error_message": error_message,
        "metadata": {},
        "start_time": "2024-01-01T10:00:00",
        "end_time": None,
    }


def _run(celery_state: str, meta_status: str, task_info=None):
    """Run get_job_from_celery with given Celery state and Redis meta status."""
    meta = _redis_meta(meta_status)
    raw_meta = json.dumps(meta).encode()

    mock_redis = MagicMock()
    mock_redis.get.return_value = raw_meta
    mock_redis.setex = MagicMock()

    manager = _make_manager(mock_redis)

    mock_result = MagicMock()
    mock_result.state = celery_state
    mock_result.info = task_info
    mock_result.result = None

    with patch("app.core.celery_queue.AsyncResult", return_value=mock_result):
        job = manager.get_job_from_celery("test-job-id")

    return job, mock_redis


class TestWorkerRestartDetection:
    """get_job_from_celery must detect stuck jobs when the worker dies."""

    def test_pending_with_processing_meta_returns_failed(self):
        """PENDING state + 'processing' in meta → worker died → job must be 'failed'."""
        job, _ = _run(celery_state="PENDING", meta_status="processing")
        assert job is not None
        assert job.status == "failed"

    def test_pending_with_processing_meta_sets_error_message(self):
        """A meaningful error message is attached when worker death is detected."""
        job, _ = _run(celery_state="PENDING", meta_status="processing")
        assert job.error_message is not None
        assert "worker" in job.error_message.lower()

    def test_pending_with_processing_meta_persists_failed_status(self):
        """The failed state must be written back to Redis."""
        _, mock_redis = _run(celery_state="PENDING", meta_status="processing")
        assert mock_redis.setex.called
        call_args = mock_redis.setex.call_args
        saved = json.loads(call_args[0][2])
        assert saved["status"] == "failed"
        assert saved["error_message"] is not None
        assert saved["end_time"] is not None

    def test_pending_with_queued_meta_returns_queued(self):
        """PENDING state + 'queued' in meta → job is legitimately waiting → 'queued'."""
        job, _ = _run(celery_state="PENDING", meta_status="queued")
        assert job is not None
        assert job.status == "queued"

    def test_pending_with_queued_meta_does_not_write_redis(self):
        """No Redis write should happen for a genuinely queued job."""
        _, mock_redis = _run(celery_state="PENDING", meta_status="queued")
        mock_redis.setex.assert_not_called()

    def test_processing_state_persists_processing_status(self):
        """STARTED/PROCESSING state must write 'processing' back to Redis meta."""
        job, mock_redis = _run(
            celery_state="PROCESSING",
            meta_status="queued",  # meta not yet updated to "processing"
            task_info={"progress": 42.0, "start_time": "2024-01-01T10:00:00"},
        )
        assert job.status == "processing"
        assert mock_redis.setex.called
        saved = json.loads(mock_redis.setex.call_args[0][2])
        assert saved["status"] == "processing"

    def test_processing_state_already_processing_meta_no_unnecessary_write(self):
        """If meta is already 'processing' and progress unchanged, no Redis write."""
        job, mock_redis = _run(
            celery_state="PROCESSING",
            meta_status="processing",  # already up-to-date
            task_info={"progress": 42.0},  # same as meta["progress"]
        )
        assert job.status == "processing"
        mock_redis.setex.assert_not_called()
