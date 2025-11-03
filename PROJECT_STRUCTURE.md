# Project Structure

This document describes the organization of the Celluloid Vision project.

## Directory Structure

```
vision/
├── app/                          # Main application package
│   ├── __init__.py              # Package entry point
│   ├── main.py                  # FastAPI application instance
│   │
│   ├── api/                     # API layer
│   │   ├── __init__.py
│   │   └── routes.py            # API endpoint handlers
│   │
│   ├── core/                    # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py            # Configuration & settings
│   │   ├── dependencies.py      # Shared dependencies (singletons)
│   │   ├── background.py        # Background task processing
│   │   ├── rq_queue.py          # Redis Queue job manager
│   │   ├── results_index.py     # Results indexing
│   │   └── utils.py             # Utility functions
│   │
│   ├── detection/               # Detection logic
│   │   ├── __init__.py
│   │   ├── detect_objects.py    # Object detection (MediaPipe)
│   │   └── scenes.py            # Scene detection
│   │
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   ├── schemas.py           # Detection schemas
│   │   └── result_models.py     # API response models
│   │
│   └── tests/                   # Test modules
│       ├── __init__.py
│       └── test_web_service.py  # API integration tests
│
├── detect.py                     # CLI entry point for video detection
├── run_app.py                    # API server entry point
├── README.md                     # Documentation
└── pyproject.toml               # Project configuration

```

## Module Descriptions

### Entry Points

#### `detect.py`
Command-line interface for single video analysis. Use this for processing individual videos without starting the API server.

```bash
python detect.py video.mp4 --output results.json
```

#### `run_app.py`
Starts the FastAPI web service for processing multiple videos with job queuing.

```bash
python run_app.py
```

### `app/` Package

#### `app/main.py`
- FastAPI application instance
- Application lifecycle management (startup/shutdown)
- Middleware configuration (CORS)
- Static files serving
- API documentation endpoint

#### `app/api/`
API endpoint handlers:
- `POST /analyse` - Start video analysis
- `GET /status/{job_id}` - Get job status
- `GET /results/{job_id}` - Get analysis results
- `GET /health` - Health check
- `GET /jobs` - List all jobs
- `GET /queue` - Get queue status

#### `app/core/`
Core application logic:
- **config.py** - Environment variables and configuration
- **dependencies.py** - Shared singleton instances (job_manager)
- **background.py** - Background job processing and callbacks
- **rq_queue.py** - Redis Queue integration for job management
- **results_index.py** - Persistent results storage and retrieval
- **utils.py** - Utility functions (version info, etc.)

#### `app/detection/`
Detection and analysis:
- **detect_objects.py** - Object detection using MediaPipe
  - Video processing
  - Object tracking
  - Sprite sheet generation
  - Face detection
- **scenes.py** - Scene detection using PySceneDetect

#### `app/models/`
Data models and schemas:
- **schemas.py** - Detection results, job status, bounding boxes
- **result_models.py** - Pydantic models for API requests/responses

#### `app/tests/`
Test modules:
- **test_web_service.py** - API integration tests with callback testing

## Import Paths

All imports now use absolute paths from the `app` package:

```python
# Detection
from app.detection.detect_objects import ObjectDetector, download_video
from app.detection.scenes import detect_scenes

# Models
from app.models.schemas import DetectionResults, JobStatus
from app.models.result_models import AnalysisRequest, AnalysisResponse

# Core utilities
from app.core.utils import get_version
from app.core.results_index import update_result_index, get_result_from_index
from app.core.rq_queue import RQJobManager

# API
from app.main import app
```

## Running the Application

### CLI Mode (Single Video)
```bash
python detect.py path/to/video.mp4 --output results.json --min-score 0.85
```

### API Server Mode (Multiple Videos with Queuing)
```bash
python run_app.py
# Server starts on http://localhost:8081
```

## Benefits of This Structure

1. **Clear Organization**: Easy to find specific functionality
2. **Modular Design**: Each module has a single, clear responsibility
3. **Maintainable**: Changes are isolated to specific modules
4. **Testable**: Modules can be tested independently
5. **Scalable**: Easy to add new features or endpoints
6. **Standard**: Follows Python package best practices
