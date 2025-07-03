import os
import json
from typing import List, Optional
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector, ThresholdDetector
from detect_objects import download_file, ensure_dir
from datetime import datetime
from urllib.parse import urlparse
from pydantic import BaseModel


class SceneInfo(BaseModel):
    """Represents a single scene in the video"""

    scene_id: int
    start_time: str
    end_time: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float


class SceneDetection(BaseModel):
    """Type definition for scene detection results"""

    total_scenes: int
    scenes: List[SceneInfo]


def detect_scenes_from_file(
    video_path: str, threshold=30.0, save_json: bool = False
) -> Optional[SceneDetection]:
    """
    Download video from URL and detect scenes

    Args:
        video_path: Path of the video to process
        threshold: Content detection threshold (default: 30.0)
        save_json: Whether to save results to JSON file (default: False)

    Returns:
        SceneDetection or None: Scene detection results
    """
    try:
        # Use the downloaded video for scene detection
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=30.0))
        scene_manager.add_detector(ThresholdDetector(threshold=12.0, min_scene_len=15))

        scene_manager.detect_scenes(video)

        scenes = scene_manager.get_scene_list()
        print(f"Detected {len(scenes)} scenes")

        # Convert scenes to SceneInfo objects
        scenes_data = []
        for i, (start_time, end_time) in enumerate(scenes):
            scene_info = SceneInfo(
                scene_id=i,
                start_time=str(start_time),
                end_time=str(end_time),
                start_seconds=start_time.get_seconds(),
                end_seconds=end_time.get_seconds(),
                duration_seconds=(end_time - start_time).get_seconds(),
            )
            scenes_data.append(scene_info)

        # Create output data structure
        output_data = SceneDetection(total_scenes=len(scenes), scenes=scenes_data)
        return output_data

    except Exception as e:
        print(f"Error detecting scenes: {str(e)}")
        return None


# Example usage
if __name__ == "__main__":
    video_url = "https://video.mshparisnord.fr/static/streaming-playlists/hls/eff0a3a5-5b2a-4e7b-b6e7-177198779081/8e8d5317-431c-4661-90d7-a6f62f1b6641-720-fragmented.mp4"

    # Create tmp folder
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
    ensure_dir(tmp_dir)

    # Download video to tmp folder
    filename = os.path.basename(urlparse(video_url).path)
    if not filename or "." not in filename:
        filename = "video.mp4"

    # Add timestamp to avoid conflicts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(filename)
    unique_filename = f"{name}_{timestamp}{ext}"
    video_path = os.path.join(tmp_dir, unique_filename)

    print(f"Downloading video to: {video_path}")
    download_file(video_url, video_path)

    # Detect scenes and save to JSON
    results = detect_scenes_from_file(video_path, threshold=30.0, save_json=True)

    output_filename = f"scene_detection_{timestamp}.json"
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
    ensure_dir(tmp_dir)
    output_path = os.path.join(tmp_dir, output_filename)

    with open(output_path, "w") as f:
        json.dump(results.model_dump_json(), f, indent=2)

    print(f"Scene detection results saved to: {output_path}")
