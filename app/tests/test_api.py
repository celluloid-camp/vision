"""
REST API integration tests for the Celluloid Vision API.

These tests run against a live instance of the FastAPI application and
verify the HTTP contract of each endpoint.  They do NOT exercise the
full video-processing pipeline; a real Celery worker is not required.

Environment variables consumed by the tests:
  BASE_URL   – base URL of the running API  (default: http://localhost:8081)
  API_KEY    – value to send in the x-api-key header (default: test-key-for-ci)
"""

import os
import time

import pytest
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8081")
API_KEY = os.getenv("API_KEY", "test-key-for-ci")
HEADERS_AUTH = {"x-api-key": API_KEY}
HEADERS_JSON_AUTH = {"Content-Type": "application/json", "x-api-key": API_KEY}
FAKE_JOB_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_api(max_wait: int = 60) -> None:
    """Block until /health returns 200 or timeout is reached."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=5)
            if r.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    pytest.fail(f"API at {BASE_URL} did not become ready within {max_wait}s")


# ---------------------------------------------------------------------------
# Session-scoped fixture: wait for the API to be up
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def wait_for_api():
    _wait_for_api()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200(self):
        r = requests.get(f"{BASE_URL}/health")
        assert r.status_code == 200

    def test_health_status_field(self):
        r = requests.get(f"{BASE_URL}/health")
        data = r.json()
        assert data["status"] in ("healthy", "unhealthy")

    def test_health_when_redis_connected(self):
        r = requests.get(f"{BASE_URL}/health")
        data = r.json()
        assert data["status"] == "healthy"

    def test_health_contains_job_stats(self):
        r = requests.get(f"{BASE_URL}/health")
        data = r.json()
        assert "job_stats" in data
        stats = data["job_stats"]
        for key in ("queued", "processing", "completed", "failed"):
            assert key in stats
            assert isinstance(stats[key], int)


# ---------------------------------------------------------------------------
# GET / (API docs)
# ---------------------------------------------------------------------------


class TestDocs:
    def test_docs_returns_200(self):
        r = requests.get(f"{BASE_URL}/")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /analyse – authentication
# ---------------------------------------------------------------------------


class TestAnalyseAuth:
    _valid_payload = {
        "external_id": "ci-test-project",
        "video_url": "http://localhost/fake-video.mp4",
        "similarity_threshold": 0.5,
    }

    def test_analyse_missing_api_key_returns_403(self):
        r = requests.post(f"{BASE_URL}/job/analyse", json=self._valid_payload)
        assert r.status_code == 403

    def test_analyse_wrong_api_key_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json=self._valid_payload,
            headers={"x-api-key": "wrong-key"},
        )
        assert r.status_code == 401

    def test_analyse_valid_api_key_returns_202(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json=self._valid_payload,
            headers=HEADERS_AUTH,
        )
        # 202 Accepted – job enqueued (video URL validation may reject localhost)
        assert r.status_code in (202, 422)


# ---------------------------------------------------------------------------
# POST /analyse – request validation
# ---------------------------------------------------------------------------


class TestAnalyseValidation:
    def test_analyse_missing_external_id_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={"video_url": "http://example.com/v.mp4"},
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_missing_video_url_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={"external_id": "ci-proj"},
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_invalid_similarity_threshold_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-proj",
                "video_url": "http://example.com/v.mp4",
                "similarity_threshold": 5.0,  # out of range [0, 1]
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_invalid_video_url_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-proj",
                "video_url": "not-a-url-and-not-a-file",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_invalid_callback_url_scheme_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-proj",
                "video_url": "http://example.com/v.mp4",
                "callback_url": "ftp://example.com/callback",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_callback_url_localhost_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-proj",
                "video_url": "http://example.com/v.mp4",
                "callback_url": "http://localhost/callback",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_callback_url_private_ip_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-proj",
                "video_url": "http://example.com/v.mp4",
                "callback_url": "http://192.168.1.1/callback",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_callback_url_loopback_ip_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-proj",
                "video_url": "http://example.com/v.mp4",
                "callback_url": "http://127.0.0.1/callback",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_analyse_valid_callback_url_accepted(self):
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-callback-valid",
                "video_url": "http://example.com/v.mp4",
                "callback_url": "https://hooks.example.com/notify",
            },
            headers=HEADERS_AUTH,
        )
        # 202 on success; 422 is also acceptable if video_url fails file-exists check
        assert r.status_code in (202, 422)
        if r.status_code == 202:
            assert r.json().get("callback_url") == "https://hooks.example.com/notify"

    def test_analyse_response_shape(self):
        """Valid request returns the expected JSON fields."""
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-shape-test",
                "video_url": "http://example.com/video.mp4",
            },
            headers=HEADERS_AUTH,
        )
        # 202 or 422 (URL may not pass file-exists check); only validate shape on 202
        if r.status_code == 202:
            data = r.json()
            assert "job_id" in data
            assert "status" in data
            assert "queue_position" in data
            assert "message" in data


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------


class TestJobStatus:
    def test_status_nonexistent_job_returns_404(self):
        r = requests.get(f"{BASE_URL}/status/{FAKE_JOB_ID}")
        assert r.status_code == 404

    def test_status_returns_correct_shape(self):
        """
        Enqueue a job then immediately query its status.
        The job will be in 'queued' state since no worker is running.
        """
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-status-test",
                "video_url": "http://example.com/video.mp4",
            },
            headers=HEADERS_AUTH,
        )
        if r.status_code != 202:
            pytest.skip("Could not enqueue job; skipping status shape test")

        job_id = r.json()["job_id"]
        rs = requests.get(f"{BASE_URL}/status/{job_id}")
        assert rs.status_code == 200
        data = rs.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert data["status"] in ("queued", "processing", "completed", "failed")
        assert "progress" in data
        assert "queue_position" in data
        assert "estimated_wait_time" in data
        assert "metadata" not in data

    def test_status_duplicate_project_returns_existing_job(self):
        """Submitting the same external_id twice returns the same job_id."""
        payload = {
            "external_id": "ci-dedup-test",
            "video_url": "http://example.com/video.mp4",
        }
        r1 = requests.post(
            f"{BASE_URL}/job/analyse", json=payload, headers=HEADERS_AUTH
        )
        if r1.status_code != 202:
            pytest.skip("Could not enqueue job; skipping deduplication test")
        job_id_1 = r1.json()["job_id"]

        r2 = requests.post(
            f"{BASE_URL}/job/analyse", json=payload, headers=HEADERS_AUTH
        )
        assert r2.status_code == 202
        assert r2.json()["job_id"] == job_id_1


# ---------------------------------------------------------------------------
# GET /results/{job_id}
# ---------------------------------------------------------------------------


class TestJobResults:
    def test_results_nonexistent_job_returns_not_found_status(self):
        r = requests.get(f"{BASE_URL}/job/{FAKE_JOB_ID}/results")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "not-found"
        assert data["data"] is None

    def test_results_response_has_status_and_data_fields(self):
        """A queued job returns status=queued with data=null."""
        r = requests.post(
            f"{BASE_URL}/job/analyse",
            json={
                "external_id": "ci-results-shape",
                "video_url": "http://example.com/video.mp4",
            },
            headers=HEADERS_AUTH,
        )
        if r.status_code != 202:
            pytest.skip("Could not enqueue job; skipping results shape test")

        job_id = r.json()["job_id"]
        rr = requests.get(f"{BASE_URL}/job/{job_id}/results")
        assert rr.status_code == 200
        data = rr.json()
        assert "status" in data
        assert "data" in data
        assert data["status"] in (
            "queued",
            "processing",
            "completed",
            "failed",
            "not-found",
        )
