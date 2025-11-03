# Application Structure

This directory contains the refactored FastAPI application with a modular structure.

## Directory Structure

```
app/
├── __init__.py                 # Package initialization
├── main.py                     # Main FastAPI application
├── api/
│   ├── __init__.py
│   └── routes.py              # API endpoint handlers
├── core/
│   ├── __init__.py
│   ├── config.py              # Application configuration
│   ├── dependencies.py        # Shared dependencies (e.g., job_manager)
│   └── background.py          # Background tasks and job processing
└── models/
    ├── __init__.py
    ├── schemas.py             # Detection schemas and JobStatus
    └── result_models.py       # Pydantic models for API responses

```

## Module Descriptions

### `app/main.py`
- Main FastAPI application instance
- Application lifecycle management (startup/shutdown)
- CORS middleware configuration
- Static files mounting
- API documentation endpoint

### `app/api/routes.py`
- API endpoint handlers:
  - `/health` - Health check
  - `/analyse` - Start video analysis
  - `/status/{job_id}` - Get job status
  - `/results/{job_id}` - Get job results
  - `/jobs` - List all jobs
  - `/queue` - Get queue status

### `app/core/config.py`
- Application configuration
- Environment variable management
- API key settings

### `app/core/dependencies.py`
- Shared dependencies
- Job manager singleton

### `app/core/background.py`
- Background job processing
- Video processing logic
- Callback handling
- Process pool management

### `app/models/`
- Data models and schemas
- Request/response models
- Job status tracking

## Running the Application

```bash
# Using the run script
python run_app.py

# Or directly with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

## Benefits of This Structure

1. **Separation of Concerns**: Each module has a clear responsibility
2. **Maintainability**: Easier to locate and modify specific functionality
3. **Testability**: Modules can be tested independently
4. **Scalability**: Easy to add new routes or features
5. **Code Organization**: Follows FastAPI best practices
