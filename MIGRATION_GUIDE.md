# Migration Guide: Old app.py → New app/ Structure

This document explains the changes made during the refactoring and how to adapt to the new structure.

## What Changed?

The monolithic `app.py` file (767 lines) has been refactored into a modular structure under the `app/` directory.

### Before (Old Structure)
```
app.py                    # Everything in one file
├── Imports
├── Configuration
├── FastAPI app setup
├── Background tasks
├── API routes
└── Helper functions
```

### After (New Structure)
```
app/
├── main.py              # FastAPI app instance & lifecycle
├── api/
│   └── routes.py        # All API endpoint handlers
├── core/
│   ├── config.py        # Configuration & settings
│   ├── dependencies.py  # Shared dependencies
│   └── background.py    # Background tasks & processing
└── models/
    ├── schemas.py       # Detection schemas
    └── result_models.py # Response models
```

## Import Changes

### If you were importing the app:

**Old:**
```python
from app import app
```

**New:**
```python
from app.main import app
# or
from app import app
```

### If you were importing models:

**Old:**
```python
from detection_schemas import DetectionResults, JobStatus
from result_models import AnalysisRequest
```

**New:**
```python
from app.models.schemas import DetectionResults, JobStatus
from app.models.result_models import AnalysisRequest
# or
from app.models import DetectionResults, JobStatus, AnalysisRequest
```

### If you were importing the job manager:

**New:**
```python
from app.core.dependencies import job_manager
# or
from app.core import job_manager
```

## Running the Application

No changes needed! Use the same commands:

```bash
# Using the run script (recommended)
python run_app.py

# Or directly with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

## Docker

The Dockerfile has been updated to use `app.main:app` instead of `app:app`.

## Backwards Compatibility

The old `app.py`, `detection_schemas.py`, and `result_models.py` files remain in the root directory for now to maintain backwards compatibility. They will be removed in a future update once all integrations are confirmed to work with the new structure.

## Benefits of the New Structure

1. **Better Code Organization**: Each module has a clear, single responsibility
2. **Easier Navigation**: Find specific functionality quickly
3. **Improved Maintainability**: Changes are isolated to specific modules
4. **Better Testing**: Each module can be tested independently
5. **Scalability**: Easy to add new routes or features
6. **Follows Best Practices**: Aligns with FastAPI project structure recommendations

## Testing Your Code

If you have custom code that imports from the old structure:

1. Update imports to use the new `app.` prefix
2. Run your tests to ensure everything works
3. Check for any deprecation warnings

## Questions?

If you encounter any issues with the migration, please open an issue in the repository.
