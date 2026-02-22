"""Shared utilities"""

import logging
import os
import sys
import tempfile
from urllib.parse import urlparse

import requests


def ensure_dir(directory: str) -> None:
    """Ensure directory exists, create if it doesn't."""
    if not os.path.exists(directory):
        os.makedirs(directory)


def download_file(url: str, local_path: str) -> str:
    """Download file from URL and return local path."""
    log = logging.getLogger(__name__)
    log.info("Downloading file from %s", url)

    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024 * 1024  # 1MB chunks

    with open(local_path, "wb") as f:
        downloaded = 0
        for data in response.iter_content(block_size):
            downloaded += len(data)
            f.write(data)
            if total_size > 0:
                done = int(50 * downloaded / total_size)
                sys.stdout.write(
                    f"\rDownloading: [{'=' * done}{' ' * (50-done)}] {downloaded}/{total_size} bytes"
                )
                sys.stdout.flush()

    print()  # New line after progress bar
    log.info("Download complete: %s", local_path)
    return local_path


def download_video(url: str) -> str:
    """Download video from URL and return local path."""
    filename = os.path.basename(urlparse(url).path)
    if not filename:
        filename = "video.mp4"
    local_path = os.path.join(tempfile.gettempdir(), filename)
    return download_file(url, local_path)


def get_log_level() -> int:
    """Return logging level from LOG_LEVEL env (default INFO)."""
    name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    return getattr(logging, name, logging.INFO)


# Read version from VERSION file
def get_version():
    try:
        with open("VERSION", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.0.0"  # fallback version
