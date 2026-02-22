#!/usr/bin/env python3
"""
Run the Celery worker (same as in .github/workflows/test.yml).
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Same as test.yml: celery -A app.core.celery_app worker --loglevel=info --queues=... --concurrency=1
queue = os.getenv("CELERY_QUEUE_NAME", "celluloid_video_processing")

os.execvp(
    sys.executable,
    [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.core.celery_app",
        "worker",
        "--loglevel=info",
        f"--queues={queue}",
        "--concurrency=1",
    ],
)
