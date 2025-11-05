# GitHub Copilot Instructions for Celluloid Vision

## Project Overview

Celluloid Vision is a video detection and analysis application powered by MediaPipe and scenedetect. It provides person detection, tracking, and timeline visualization through a FastAPI-based REST API with asynchronous job processing using Redis Queue (RQ).

## Technology Stack

- **Language**: Python 3.12 (MediaPipe doesn't support Python 3.13+ yet)
- **Web Framework**: FastAPI 0.104.1
- **Computer Vision**: MediaPipe (>=0.10.0), OpenCV (>=4.8.0)
- **Scene Detection**: scenedetect (0.6.6)
- **Job Queue**: Redis (>=5.0.1) with RQ (>=1.15.1)
- **API Documentation**: Scalar FastAPI
- **Server**: Hypercorn/Uvicorn
- **Data Validation**: Pydantic
- **Package Management**: uv (preferred)

## Development Environment Setup

### Prerequisites
- Python 3.12 (required - MediaPipe limitation)
- Redis server (for job queue)
- uv package manager (recommended)

### Installation
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies with uv
uv pip install -e .

# Or with virtual environment
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

### Running the Application
```bash
# Using uv (recommended)
uv run python run_app.py

# The service starts on http://localhost:8081
```

## Code Style and Standards

### Formatting
- **Black**: Auto-formatter with default settings
- **Line Length**: Maximum 200 characters (configured in .flake8)
- Use Black for all Python files before committing

### Linting
- **Flake8**: Linter with max line length of 200
- Run `uv run flake8 {files}` to check code quality
- Pre-commit hooks configured via lefthook.yml

### Pre-commit Hooks
The project uses Lefthook for pre-commit hooks:
- `python-format`: Runs Black on staged Python files
- `python-lint`: Runs Flake8 on staged Python files

## Architecture and Design Patterns

### Project Structure

The project uses a flat structure with all Python modules in the root directory:

**Core Application Files:**
- `app.py`: FastAPI application with API endpoints
- `run_app.py`: Entry point script to start the application with Uvicorn
- `detect_objects.py`: Core object detection logic using MediaPipe
- `scenes.py`: Scene detection functionality using scenedetect
- `rq_queue.py`: RQ job manager for async processing

**Data Models:**
- `detection_schemas.py`: Pydantic models for detection data structures
- `result_models.py`: Pydantic models for API request/response

**Utilities:**
- `results_index.py`: Persistent results storage helpers
- `utils.py`: Shared utility functions

**Testing:**
- `test_web_service.py`: Integration test suite

**Configuration Files:**
- `pyproject.toml`: Python project configuration and dependencies
- `lefthook.yml`: Pre-commit hooks configuration
- `.flake8`: Flake8 linting configuration
- `env.example`: Example environment variables
- `Dockerfile`: Container configuration for deployment
- `deploy.sh`: Deployment script

**Documentation:**
- `README.md`: Main project documentation
- `README-fr.md`: French documentation
- `Api.md`: API endpoint documentation
- `CHANGELOG.md`: Version history

**Directories:**
- `.github/workflows/`: CI/CD workflows (build.yml, release.yml)
- `samples/`: Sample detection results and sprite images

### Key Components

#### 1. API Layer (app.py)
- RESTful API built with FastAPI
- Endpoints: `/health`, `/analyse`, `/status/{job_id}`, `/results/{project_id}/{job_id}`
- API key authentication via `X-API-Key` header
- CORS middleware enabled
- Scalar API documentation at `/scalar`

#### 2. Detection Engine (detect_objects.py)
- MediaPipe-based object detection
- Person detection with face detection
- Object tracking across frames
- Thumbnail sprite generation
- Progress reporting during processing

#### 3. Scene Detection (scenes.py)
- Content-based scene detection using scenedetect
- Threshold-based scene detection
- Scene metadata with timestamps and durations

#### 4. Job Queue (rq_queue.py)
- Redis Queue for async job processing
- Job lifecycle: queued → processing → completed/failed
- Callback URL support for job completion notifications
- Job cleanup and retention policies

### Data Models

#### Detection Results Schema
```python
DetectionResults:
  - version: str
  - metadata: ResultsMetadata
    - video: VideoMetadata (fps, frame_count, dimensions)
    - model: ModelMetadata (name, type, version)
    - sprite: SpriteMetadata (thumbnail paths)
    - processing: ProcessingMetadata (timing, statistics)
  - frames: List[DetectionFrame]
    - frame_idx, timestamp
    - objects: List[DetectionObject]
      - id, class_name, confidence, bbox, thumbnail
```

#### Job Status
- States: queued, processing, completed, failed
- Tracks: job_id, project_id, video_url, similarity_threshold
- Metadata: progress, timestamps, error messages

### API Patterns

#### Request/Response Flow
1. Client POSTs to `/analyse` with video URL and parameters
2. Job is queued in Redis Queue (RQ)
3. Worker processes video asynchronously
4. Results stored with project_id and job_id as keys
5. Optional callback URL is notified on completion
6. Client polls `/status/{job_id}` or gets notified via callback
7. Client retrieves results from `/results/{project_id}/{job_id}`

#### Error Handling
- Use HTTPException with appropriate status codes
- Log errors with context using Python logging
- Include error messages in job metadata
- Failed jobs moved to RQ FailedJobRegistry

## Testing

### Test Files
- `test_web_service.py`: Integration tests for the web service
- Tests callback functionality with Flask mock server
- Validates API endpoints and job processing flow

### Running Tests
```bash
# Run the test suite
uv run python test_web_service.py
```

## Environment Configuration

### Required Environment Variables
- `REDIS_URL`: Redis connection URL (required)
- `RQ_QUEUE_NAME`: Queue name (default: "celluloid_video_processing")
- `RQ_JOB_TIMEOUT`: Job timeout in seconds (default: 3600)
- `API_KEY`: API authentication key
- `PORT`: Server port (default: 8081)

### Configuration Files
- `.env`: Environment variables (not committed)
- `env.example`: Example environment configuration

## MediaPipe Integration

### Models Used
- Object detection: efficientdet_lite0
- Face detection: BlazeFace (integrated within person detection workflow)
- Models downloaded automatically on first use
- Focus: Person detection with face detection to distinguish persons with/without faces

### Detection Parameters
- `similarity_threshold`: Object tracking threshold (0.0-1.0, default: 0.5)
- Higher threshold (0.7-0.9) = stricter matching between frames, requires more visual similarity for tracking the same object across frames, reduces false positives but may lose track more easily
- Lower threshold (0.3-0.5) = more lenient tracking, maintains tracking even with appearance changes, may have more false positives but better continuity
- Recommended: 0.5 for general use, 0.7+ for static cameras, 0.3-0.4 for dynamic scenes

## Best Practices

### When Adding New Features

1. **API Endpoints**
   - Define Pydantic models in `result_models.py`
   - Add endpoint to `app.py` with proper error handling
   - Include API key authentication if needed
   - Update API documentation

2. **Detection Logic**
   - Add new detection functions to `detect_objects.py`
   - Follow existing pattern: process video → extract features → return structured data
   - Include progress reporting for long-running operations
   - Handle video download and cleanup

3. **Job Processing**
   - Queue jobs through `RQJobManager`
   - Update job metadata during processing
   - Handle callbacks on completion/failure
   - Clean up temporary files

4. **Data Models**
   - Use Pydantic BaseModel for data validation
   - Define schemas in `detection_schemas.py`
   - Include type hints for all fields
   - Document field purposes with docstrings

### Code Quality

- Always use type hints for function parameters and return values
- Include docstrings for classes and complex functions
- Use descriptive variable names
- Log important events and errors with appropriate levels
- Handle exceptions gracefully with try/except
- Clean up resources (files, connections) properly

### Security Considerations

- Never commit API keys or secrets to the repository
- Use environment variables for sensitive configuration
- Validate and sanitize user inputs
- Implement proper authentication for API endpoints
- Be cautious with file operations (path traversal, cleanup)

### Performance

- Use async/await for I/O operations
- Process videos in chunks/frames to avoid memory issues
- Clean up temporary files after processing
- Consider job timeout limits for large videos
- Use Redis for job state to enable horizontal scaling

## Common Tasks

### Adding a New Detection Feature
1. Add detection logic to `detect_objects.py`
2. Define data model in `detection_schemas.py`
3. Update API response model in `result_models.py`
4. Add endpoint or extend existing in `app.py`
5. Test with `test_web_service.py`

### Adding a New API Endpoint
1. Define request/response models in `result_models.py`
2. Add endpoint to `app.py` with proper decorators
3. Implement business logic or delegate to existing modules
4. Add error handling and logging
5. Test endpoint functionality

### Modifying Detection Parameters
1. Update function signatures in `detect_objects.py`
2. Update `AnalysisRequest` model in `result_models.py`
3. Update API documentation in `Api.md`
4. Update or add tests in `test_web_service.py` to validate new parameters
5. Test with various parameter values to ensure backward compatibility

## Deployment

### Docker
- Dockerfile provided for containerized deployment
- Build workflow: `.github/workflows/build.yml`
- Images pushed to GitHub Container Registry

### Production Considerations
- Ensure Redis is properly configured and accessible
- Set appropriate RQ_JOB_TIMEOUT for expected video sizes
- Configure API_KEY for authentication
- Monitor disk space for temporary video files
- Scale RQ workers based on load

## Additional Resources

- API Documentation: See `Api.md` for detailed endpoint specifications
- Changelog: See `CHANGELOG.md` for version history
- MediaPipe Documentation: https://developers.google.com/mediapipe
- FastAPI Documentation: https://fastapi.tiangolo.com/
- RQ Documentation: https://python-rq.org/
