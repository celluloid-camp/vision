#!/bin/bash

# Celluloid Video Analysis API Deployment Script

set -e

echo "🚀 Deploying Celluloid Video Analysis API..."

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t celluloid-video-analysis-api .

# Stop existing container if running
echo "🛑 Stopping existing container..."
docker stop celluloid-video-analysis-api 2>/dev/null || true
docker rm celluloid-video-analysis-api 2>/dev/null || true

# Run the container
echo "🏃 Starting container..."
docker run -d \
    --name celluloid-video-analysis-api \
    --restart unless-stopped \
    -p 8080:8080 \
    -v "$(pwd)/outputs:/app/outputs" \
    -v "$(pwd)/models:/app/models:ro" \
    -e REDIS_URL="redis://localhost:6379/0" \
    celluloid-video-analysis-api

# Wait for service to be ready
echo "⏳ Waiting for service to be ready..."
for i in {1..30}; do
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        echo "✅ Service is ready!"
        break
    fi
    echo "   Waiting... ($i/30)"
    sleep 2
done

# Show container status
echo "📊 Container status:"
docker ps --filter name=celluloid-video-analysis-api

echo ""
echo "🎉 Deployment complete!"
echo "📡 API is available at: http://localhost:8080"
echo "🔍 Health check at: http://localhost:8080/health"
echo ""
echo "📋 Useful commands:"
echo "   View logs: docker logs -f celluloid-video-analysis-api"
echo "   Stop service: docker stop celluloid-video-analysis-api"
echo "   Restart service: docker restart celluloid-video-analysis-api"
echo "   Remove service: docker rm -f celluloid-video-analysis-api" 