### API Endpoints

#### 1. Health Check

```http
GET /health
```

**Response**:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00",
  "queue_size": 2,
  "processing_jobs": 1,
  "current_job": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### 2. Start Detection

```http
POST /analyse
Content-Type: application/json

{
  "external_id": "my_project_001",
  "video_url": "https://example.com/video.mp4",
  "similarity_threshold": 0.6,
  "callback_url": "https://myapp.com/webhooks/analysis-complete"
}
```

**Parameters**:

- `external_id` (required): Unique identifier for organizing results
- `video_url` (required): URL or local path to video file
- `similarity_threshold` (optional): Threshold for object tracking (0.0-1.0,
  default: 0.5)
- `callback_url` (optional): URL to call when analysis completes or fails

**Response**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "queue_position": 2,
  "message": "Object detection job added to queue",
  "callback_url": "https://myapp.com/webhooks/analysis-complete"
}
```

#### 3. Get Job Status

```http
GET /status/{job_id}
```

**Response**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "my_project_001",
  "video_url": "https://example.com/video.mp4",
  "similarity_threshold": 0.6,
  "status": "processing",
  "progress": 45.2,
  "start_time": "2024-01-15T10:30:00",
  "metadata": {
    "frames_processed": 450,
    "frames_with_detections": 23,
    "total_detections": 67,
    "processing_time": 45.2
  }
}
```

**For queued jobs**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "my_project_001",
  "video_url": "https://example.com/video.mp4",
  "similarity_threshold": 0.6,
  "status": "queued",
  "progress": 0.0,
  "queue_position": 2,
  "estimated_wait_time": "~10 minutes"
}
```

#### 4. Get Job Results

```http
GET /results/{job_id}
```

**Response**: Full TAO format detection results including:

- Video metadata
- Model information
- Processing metadata
- Frames with detections
- Object tracking data
- Sprite thumbnail references

#### 5. List Jobs

```http
GET /jobs?external_id=my_project_001&status=completed
```

**Query Parameters**:

- `external_id` (optional): Filter by project ID
- `status` (optional): Filter by job status (queued, processing, completed,
  failed)

**Response**:

```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "external_id": "my_project_001",
      "status": "completed",
      "progress": 100.0,
      "start_time": "2024-01-15T10:30:00",
      "end_time": "2024-01-15T10:35:00"
    }
  ],
  "total": 1,
  "queue_size": 2,
  "processing_jobs": 1
}
```

#### 6. Get Queue Status

```http
GET /queue
```

**Response**:

```json
{
  "queue_size": 2,
  "processing_jobs": 1,
  "current_job": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "external_id": "my_project_001",
    "start_time": "2024-01-15T10:30:00"
  },
  "queued_jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440001",
      "external_id": "my_project_002",
      "queue_position": 1,
      "estimated_wait_time": "~5 minutes"
    },
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440002",
      "external_id": "my_project_003",
      "queue_position": 2,
      "estimated_wait_time": "~10 minutes"
    }
  ]
}
```

#### 7. Delete Job

```http
DELETE /jobs/{job_id}
```

**Response**:

```json
{
  "message": "Job deleted successfully"
}
```

## Example Usage

### Using curl

1. **Start a detection job**:
   ```bash
   curl -X POST http://localhost:5000/analyse \
     -H "Content-Type: application/json" \
     -d '{
       "external_id": "test_project",
       "video_url": "https://storage.googleapis.com/mediapipe-assets/portrait.mp4",
       "similarity_threshold": 0.6,
       "callback_url": "https://myapp.com/webhooks/analysis-complete"
     }'
   ```

2. **Check queue status**:
   ```bash
   curl http://localhost:5000/queue
   ```

3. **Check job status**:
   ```bash
   curl http://localhost:5000/status/550e8400-e29b-41d4-a716-446655440000
   ```

4. **Get results**:
   ```bash
   curl http://localhost:5000/results/550e8400-e29b-41d4-a716-446655440000
   ```

### Using Python

```python
import requests
import time

# Start detection
response = requests.post('http://localhost:5000/analyse', json={
    'external_id': 'my_project',
    'video_url': 'https://example.com/video.mp4',
    'similarity_threshold': 0.6,
    'callback_url': 'https://myapp.com/webhooks/analysis-complete'
})

job_id = response.json()['job_id']
print(f"Job queued with ID: {job_id}")

# Check queue status
queue_response = requests.get('http://localhost:5000/queue')
queue_data = queue_response.json()
print(f"Queue size: {queue_data['queue_size']}")

# Wait for completion
while True:
    status_response = requests.get(f'http://localhost:5000/status/{job_id}')
    status = status_response.json()['status']
    
    if status == 'completed':
        break
    elif status == 'failed':
        print('Job failed!')
        break
    elif status == 'queued':
        position = status_response.json().get('queue_position', 0)
        print(f'Job in queue at position {position}')
    
    time.sleep(10)

# Get results
results = requests.get(f'http://localhost:5000/results/{job_id}').json()
print(f"Found {len(results['frames'])} frames with detections")
```

## Testing

Run the test script to verify the service:

```bash
python test_web_service.py
```

## Queue System

The web service implements a queue system to ensure only one job runs at a time:

- **Job States**: `queued` → `processing` → `completed`/`failed`
- **Queue Position**: Jobs are processed in FIFO order
- **Wait Time Estimation**: Rough estimate based on queue position
- **Resource Management**: Prevents memory and CPU conflicts
- **Job Cancellation**: Queued jobs can be cancelled, processing jobs cannot

## Output Structure

Results are saved in the `outputs/{external_id}/` directory with the following
structure:

```
outputs/
├── project_001/
│   ├── detections_550e8400-e29b-41d4-a716-446655440000_20240115_103000.json
│   └── sprite_550e8400-e29b-41d4-a716-446655440000_20240115_103000.png
└── project_002/
    └── ...
```

## Configuration

### Environment Variables

- `API_KEY`: Set to in the .env file
- `REDIS_URL`: Redis URL (default: redis://localhost:6379/0)

### Callback Notifications

When a `callback_url` is provided, the service will send a POST request to that
URL when the analysis completes or fails.

**Success Callback Payload**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "my_project_001",
  "status": "completed",
  "timestamp": "2024-01-15T10:35:00",
  "results": {
    "result_path": "outputs/my_project_001/detections_550e8400-e29b-41d4-a716-446655440000_20240115_103000.json",
    "metadata": {
      "frames_processed": 450,
      "frames_with_detections": 23,
      "total_detections": 67,
      "processing_time": 45.2
    }
  }
}
```

**Failure Callback Payload**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "my_project_001",
  "status": "failed",
  "timestamp": "2024-01-15T10:35:00",
  "error": "Failed to download video: HTTP 404 Not Found"
}
```
