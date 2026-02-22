#!/bin/bash

# Celluloid Video Analysis API Deployment Script

set -e

echo "🚀 Deploying Celluloid Video Analysis API..."

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t celluloid-video-analysis-api .

# Stop existing containers if running
echo "🛑 Stopping existing containers..."
docker stop celluloid-video-analysis-api celluloid-video-analysis-worker 2>/dev/null || true
docker rm celluloid-video-analysis-api celluloid-video-analysis-worker 2>/dev/null || true

# Run the API container
echo "🏃 Starting API container..."
docker run -d \
    --name celluloid-video-analysis-api \
    --restart unless-stopped \
    -p 8081:8081 \
    -v "$(pwd)/outputs:/app/outputs" \
    -v "$(pwd)/models:/app/models:ro" \
    -e REDIS_URL="redis://host.docker.internal:6379/0" \
    -e API_KEY="xxx" \
    -e CELERY_QUEUE_NAME="celluloid_video_processing" \
    -e CELERY_TASK_TIMEOUT="3000" \
    celluloid-video-analysis-api

# Run the Celery worker container (same as .github/workflows/test.yml)
echo "🏃 Starting Celery worker container..."
docker run -d \
    --name celluloid-video-analysis-worker \
    --restart unless-stopped \
    -v "$(pwd)/outputs:/app/outputs" \
    -v "$(pwd)/models:/app/models:ro" \
    -e REDIS_URL="redis://host.docker.internal:6379/0" \
    -e API_KEY="xxx" \
    -e CELERY_QUEUE_NAME="celluloid_video_processing" \
    -e CELERY_TASK_TIMEOUT="3000" \
    celluloid-video-analysis-api \
    celery -A app.core.celery_app worker \
        --loglevel=info \
        --queues=celluloid_video_processing \
        --concurrency=1

# Wait for service to be ready
echo "⏳ Waiting for service to be ready..."
for i in {1..30}; do
    if curl -f http://localhost:8081/health > /dev/null 2>&1; then
        echo "✅ Service is ready!"
        break
    fi
    echo "   Waiting... ($i/30)"
    sleep 2
done

# Show container status
echo "📊 Container status:"
docker ps --filter name=celluloid-video-analysis

echo ""
echo "🎉 Deployment complete!"
echo "📡 API is available at: http://localhost:8081"
echo "🔍 Health check at: http://localhost:8081/health"
echo ""
echo "📋 Useful commands:"
echo "   API logs:    docker logs -f celluloid-video-analysis-api"
echo "   Worker logs: docker logs -f celluloid-video-analysis-worker"
echo "   Stop:        docker stop celluloid-video-analysis-api celluloid-video-analysis-worker"
echo "   Restart:     docker restart celluloid-video-analysis-api celluloid-video-analysis-worker"
echo "   Remove:      docker rm -f celluloid-video-analysis-api celluloid-video-analysis-worker" 