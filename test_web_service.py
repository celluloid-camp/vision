#!/usr/bin/env python3
"""
Test script for the MediaPipe Object Detection Web Service
"""

import requests
import json
import time
import sys
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

# Configuration
BASE_URL = "http://localhost:8081"
CALLBACK_PORT = 8082
CALLBACK_URL = f"http://localhost:8082/callback"


TEST_VIDEO_URL = "https://video.mshparisnord.fr/static/streaming-playlists/hls/eff0a3a5-5b2a-4e7b-b6e7-177198779081/8e8d5317-431c-4661-90d7-a6f62f1b6641-720-fragmented.mp4"

# Shared state for callback
callback_received = threading.Event()
callback_payload = {}

# Flask app for callback
callback_app = Flask(__name__)

# Enable CORS for all routes
CORS(callback_app, resources={r"/*": {"origins": "*"}})

@callback_app.route('/callback', methods=['POST', 'GET'])
def callback_endpoint():
    global callback_payload
    callback_payload.clear()
    
    print(f"\n[CALLBACK RECEIVED] Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    
    # Handle both POST and GET requests
    if request.method == 'POST':
        if request.is_json:
            data = request.json
        else:
            data = request.form.to_dict()
            # Try to parse form data as JSON if it's a string
            for key, value in data.items():
                if isinstance(value, str) and value.startswith('{'):
                    try:
                        data[key] = json.loads(value)
                    except:
                        pass
    else:  # GET request
        data = request.args.to_dict()
        # Try to parse query parameters as JSON if they're strings
        for key, value in data.items():
            if isinstance(value, str) and value.startswith('{'):
                try:
                    data[key] = json.loads(value)
                except:
                    pass
    
    callback_payload.update(data)
    print(f"Data received: {json.dumps(data, indent=2)}")
    callback_received.set()
    
    # Return success response
    return jsonify({"status": "received", "method": request.method}), 200

@callback_app.route('/callback', methods=['OPTIONS'])
def callback_options():
    """Handle CORS preflight requests"""
    response = jsonify({"status": "ok"})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
    return response

def run_callback_server():
    """Run the callback server with better error handling"""
    try:
        print(f"Starting callback server on port {CALLBACK_PORT}...")
        callback_app.run(
            host='0.0.0.0',  # Allow external connections
            port=CALLBACK_PORT, 
            debug=False, 
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        print(f"Error starting callback server: {e}")

def test_health_check():
    """Test the health check endpoint"""
    print("Testing health check...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Health check passed: {data}")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health check error: {e}")
        return False

def test_start_detection():
    """Test starting a detection job"""
    print("\nTesting start detection with callback...")
    
    # Sample request data
    request_data = {
        "project_id": "test_project_002",
        "video_url": TEST_VIDEO_URL,
        "similarity_threshold": 0.6,
        "callback_url": CALLBACK_URL
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/analyse",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 202:
            data = response.json()
            print(f"✓ Detection job started: {data}")
            return data.get("job_id")
        else:
            print(f"✗ Failed to start detection: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error starting detection: {e}")
        return None

def test_get_status(job_id):
    """Test getting job status"""
    print(f"\nTesting get status for job {job_id}...")
    
    try:
        response = requests.get(f"{BASE_URL}/status/{job_id}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Job status: {data}")
            return data.get("status")
        else:
            print(f"✗ Failed to get status: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error getting status: {e}")
        return None

def test_get_results(job_id):
    """Test getting job results"""
    print(f"\nTesting get results for job {job_id}...")
    
    try:
        response = requests.get(f"{BASE_URL}/results/{job_id}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Results retrieved successfully")
            print(f"  - Video: {data.get('video', {}).get('url', 'N/A')}")
            print(f"  - Frames with detections: {len(data.get('frames', []))}")
            print(f"  - Processing time: {data.get('metadata', {}).get('processing', {}).get('duration_seconds', 'N/A')} seconds")
            return True
        else:
            print(f"✗ Failed to get results: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error getting results: {e}")
        return False

def test_list_jobs():
    """Test listing all jobs"""
    print("\nTesting list jobs...")
    
    try:
        response = requests.get(f"{BASE_URL}/jobs")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Jobs listed successfully")
            print(f"  - Total jobs: {data.get('total', 0)}")
            print(f"  - Queue size: {data.get('queue_size', 0)}")
            print(f"  - Processing jobs: {data.get('processing_jobs', 0)}")
            for job in data.get('jobs', []):
                print(f"    - {job.get('job_id')}: {job.get('status')} ({job.get('project_id')})")
            return True
        else:
            print(f"✗ Failed to list jobs: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error listing jobs: {e}")
        return False

def test_queue_status():
    """Test getting queue status"""
    print("\nTesting queue status...")
    
    try:
        response = requests.get(f"{BASE_URL}/queue")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Queue status retrieved successfully")
            print(f"  - Queue size: {data.get('queue_size', 0)}")
            print(f"  - Processing jobs: {data.get('processing_jobs', 0)}")
            if data.get('current_job'):
                print(f"  - Current job: {data.get('current_job', {}).get('job_id')}")
            for job in data.get('queued_jobs', []):
                print(f"    - Position {job.get('queue_position')}: {job.get('job_id')} ({job.get('project_id')})")
            return True
        else:
            print(f"✗ Failed to get queue status: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error getting queue status: {e}")
        return False

def wait_for_completion(job_id, max_wait_time=300):
    """Wait for job completion"""
    print(f"\nWaiting for job {job_id} to complete...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        status = test_get_status(job_id)
        
        if status == "completed":
            print("✓ Job completed successfully!")
            return True
        elif status == "failed":
            print("✗ Job failed!")
            return False
        elif status == "processing":
            print("⏳ Job still processing...")
            time.sleep(10)  # Wait 10 seconds before checking again
        elif status == "queued":
            print("⏳ Job still in queue...")
            time.sleep(5)  # Wait 5 seconds before checking again
        else:
            print(f"Unknown status: {status}")
            time.sleep(5)
    
    print("⏰ Timeout waiting for job completion")
    return False

def main():
    """Run all tests"""
    print("MediaPipe Object Detection Web Service Test (Callback Mode)")
    print("=" * 50)
    
    # Start callback server in background
    callback_thread = threading.Thread(target=run_callback_server, daemon=True)
    callback_thread.start()
    print(f"Callback server running at {CALLBACK_URL}")
    time.sleep(2)  # Give Flask a moment to start

    # Test 1: Health check
    if not test_health_check():
        print("Service is not running. Please start the web service first.")
        print("Run: python app.py")
        sys.exit(1)
    
    # Test 2: Start detection with callback
    job_id = test_start_detection()
    if not job_id:
        print("Failed to start detection job. Exiting.")
        sys.exit(1)
    
    # Test 3: Check queue status
    test_queue_status()
    
    # Test 4: Wait for completion
    if wait_for_completion(job_id):
        # Test 5: Get results
        test_get_results(job_id)
    
    # Test 6: List jobs
    test_list_jobs()
    
    print("\nWaiting for callback from analysis job...")
    callback_received.wait(timeout=600)  # Wait up to 10 minutes
    if callback_received.is_set():
        print("\nTest completed: Callback received!")
        print(json.dumps(callback_payload, indent=2))
        if callback_payload.get("status") == "completed":
            print("Analysis completed successfully!")
        elif callback_payload.get("status") == "failed":
            print(f"Analysis failed: {callback_payload.get('error')}")
        else:
            print(f"Unknown callback status: {callback_payload.get('status')}")
    else:
        print("\nTest failed: No callback received within timeout.")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("Test completed!")

if __name__ == "__main__":
    main() 