# Celluloid Video Analysis API

Video detection and analysis application powered by MediaPipe and scenedetect.
Features person detection, tracking and timeline visualization.

## Installation

**Prerequisites**: Python 3.12 is required (MediaPipe doesn't support Python
3.13+ yet).

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Python 3.12** (if not already installed):
   ```bash
   # macOS (using Homebrew)
   brew install python@3.12

   # Or let uv install it automatically (recommended)
   uv python install 3.12
   ```

3. **Install Python Dependencies**:
   ```bash
   uv pip install -e .
   ```

   Or using a virtual environment with Python 3.12:
   ```bash
   uv venv --python 3.12
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .
   ```

4. **Ensure MediaPipe Models**: The service will automatically download required
   models on first use.

## Usage

### Starting the Service

#### Option 1: Using uv run (Recommended)

Run directly with uv. It will automatically use Python 3.12 as specified in
`pyproject.toml`:

```bash
uv run python run_app.py
```

If you need to explicitly specify Python 3.12:

```bash
uv run --python 3.12 python run_app.py
```

The service will start on `http://localhost:8081`
