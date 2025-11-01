import os
import json
from typing import Optional, Dict, Any

INDEX_PATH = os.path.join("outputs", "job_index.json")


def update_result_index(job_id: str, result_path: str, status: str, metadata: dict):
    """Update the persistent job index with job result info."""
    try:
        if os.path.exists(INDEX_PATH):
            with open(INDEX_PATH, "r") as f:
                index = json.load(f)
        else:
            index = {}
        index[job_id] = {
            "result_path": result_path,
            "status": status,
            "metadata": metadata,
        }
        with open(INDEX_PATH, "w") as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        print(f"Failed to update job index: {e}")


def get_result_from_index(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve DetectionResultsModel-compatible dict from the persistent job index by job_id."""
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            index = json.load(f)
        job_info = index.get(job_id)
        if job_info:
            result_path = job_info.get("result_path")
            if result_path and os.path.exists(result_path):
                with open(result_path, "r") as rf:
                    try:
                        return json.load(rf)
                    except Exception:
                        return None
            # If job failed (no result_path), return the job_info itself
            if job_info.get("status") == "failed":
                return job_info
    return None
