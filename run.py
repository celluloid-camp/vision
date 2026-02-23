#!/usr/bin/env python3
"""
Unified launcher for API, Celery worker, and Flower.
"""

import logging
import os
import signal
import subprocess
import sys
import time

from dotenv import load_dotenv

from app.core.utils import get_log_level

load_dotenv()

logging.basicConfig(level=get_log_level())
logger = logging.getLogger(__name__)


def api_command() -> list[str]:
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8081",
        "--reload",
        "--log-level",
        log_level,
    ]


def worker_command() -> list[str]:
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    queue = os.getenv("CELERY_QUEUE_NAME", "celluloid_video_processing")
    return [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.core.celery_app",
        "worker",
        "--loglevel",
        log_level,
        f"--queues={queue}",
        "--concurrency=1",
    ]


def flower_command() -> list[str]:
    flower_port = os.getenv("FLOWER_PORT", "5555")
    return [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.core.celery_app",
        "flower",
        f"--port={flower_port}",
    ]


def run_single(command: list[str], name: str) -> None:
    logger.info("Starting %s...", name)
    os.execvp(command[0], command)


def shutdown_processes(processes: dict[str, subprocess.Popen]) -> None:
    for name, proc in processes.items():
        if proc.poll() is None:
            logger.info("Stopping %s (pid=%s)...", name, proc.pid)
            proc.terminate()

    deadline = time.time() + 10
    while time.time() < deadline:
        if all(proc.poll() is not None for proc in processes.values()):
            return
        time.sleep(0.2)

    for name, proc in processes.items():
        if proc.poll() is None:
            logger.warning("%s did not stop gracefully, killing it.", name)
            proc.kill()


def run_multi(modes: list[str]) -> int:
    commands = {
        "api": api_command(),
        "worker": worker_command(),
        "flower": flower_command(),
    }

    processes: dict[str, subprocess.Popen] = {}
    stop_requested = False

    def _handle_signal(signum, _frame):
        nonlocal stop_requested
        logger.info("Received signal %s, shutting down...", signum)
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        for mode in modes:
            logger.info("Starting %s...", mode)
            processes[mode] = subprocess.Popen(commands[mode])

        while not stop_requested:
            for mode, proc in processes.items():
                code = proc.poll()
                if code is not None:
                    logger.error("%s exited with code %s", mode, code)
                    stop_requested = True
                    break
            time.sleep(0.5)
    finally:
        shutdown_processes(processes)

    return 0


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    valid = {"api", "worker", "flower", "default", "all"}
    if mode not in valid:
        print("Usage: python run.py [api|worker|flower|default|all]")
        return 1

    if mode == "api":
        run_single(api_command(), "api")
    if mode == "worker":
        run_single(worker_command(), "worker")
    if mode == "flower":
        run_single(flower_command(), "flower")
    if mode == "default":
        return run_multi(["api", "worker"])

    return run_multi(["api", "worker", "flower"])


if __name__ == "__main__":
    raise SystemExit(main())
