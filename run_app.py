#!/usr/bin/env python3
"""
Simple script to run the FastAPI app locally
"""

import uvicorn
import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    logger.info("🚀 Starting Celluloid Object Detection API with FastAPI...")
    logger.info("📡 API will be available at: http://localhost:8081")
    logger.info("🔍 Health check at: http://localhost:8081/health")
    logger.info("🔍 Redis URL: %s", os.getenv("REDIS_URL"))

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8081,
        reload=True,  # Enable auto-reload for development
        log_level="info",
    )
