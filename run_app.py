#!/usr/bin/env python3
"""
Simple script to run the FastAPI app locally
"""

import uvicorn
import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("🚀 Starting Celluloid Object Detection API with FastAPI...")
    print("📡 API will be available at: http://localhost:5000")
    print("📚 OpenAPI docs at: http://localhost:5000/docs")
    print("🔍 Health check at: http://localhost:5000/health")
    print("")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5000,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    ) 