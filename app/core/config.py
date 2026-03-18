"""Application configuration and settings"""

import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
API_VERSION = "1.0.1"

# Server Configuration
HOST = "0.0.0.0"
PORT = 8081

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Processing Configuration
MAX_WORKERS = 1  # Only 1 worker since we process one job at a time
