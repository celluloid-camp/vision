# Use Python 3.12 slim Debian image for better compatibility with MediaPipe
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# related to https://github.com/jenkinsci/docker/issues/543
RUN echo "Acquire::http::Pipeline-Depth 0;" > /etc/apt/apt.conf.d/99custom && \
    echo "Acquire::http::No-Cache true;" >> /etc/apt/apt.conf.d/99custom && \
    echo "Acquire::BrokenProxy    true;" >> /etc/apt/apt.conf.d/99custom

# Install OpenCV dependencies and Redis
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-dev \
    libgtk-3-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libv4l-dev \
    libxvidcore-dev \
    libx264-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    gfortran \
    redis-server \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files and package structure for better caching
COPY pyproject.toml README.md ./
COPY app ./app
COPY analyse.py run_app.py run_worker.py entrypoint.sh ./

# Install Python dependencies using uv
RUN uv pip install --system --no-cache -e .

# Copy remaining application code
COPY . .

# Create outputs directory
RUN mkdir -p outputs

# Entrypoint: api | worker | both
RUN chmod +x /app/entrypoint.sh

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8081

# both = worker + uvicorn (default), api = uvicorn only, worker = Celery only
ENTRYPOINT ["./entrypoint.sh"]
CMD ["both"]

