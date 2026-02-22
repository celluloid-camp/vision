import argparse
import json
import cv2
import numpy as np
from typing import Dict, Any, Tuple
import time
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import logging
import os
import sys
from datetime import datetime
import signal
import atexit
from PIL import Image

# Import detection types
from app.models.schemas import (
    DetectionResults,
)
from app.core.utils import (
    get_log_level,
    ensure_dir,
    download_file,
    download_video,
    get_version,
)

# Set up logging (level from LOG_LEVEL env, default INFO)
logging.basicConfig(level=get_log_level())
logger = logging.getLogger(__name__)


def get_model_path(model_type: str = "detector") -> str:
    """
    Get the path to the model file, downloading it if necessary
    """
    if model_type == "detector":
        model_url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite"
        model_name = "efficientdet_lite0.tflite"

    # if model_type == "detector":
    #     model_url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite"
    #     model_name = "efficientdet_lite2.tflite"
    # elif model_type == "embedder":
    #     model_url = "https://storage.googleapis.com/mediapipe-models/image_embedder/mobilenet_v3_large/float32/latest/mobilenet_v3_large.tflite"
    #     model_name = "mobilenet_v3_large.tflite"

    elif model_type == "embedder":
        model_url = "https://storage.googleapis.com/mediapipe-models/image_embedder/mobilenet_v3_small/float32/latest/mobilenet_v3_small.tflite"
        model_name = "mobilenet_v3_small.tflite"

    elif model_type == "face":
        model_url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
        model_name = "detector.tflite"

    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    ensure_dir(model_dir)
    model_path = os.path.join(model_dir, model_name)

    if not os.path.exists(model_path):
        logger.info(f"Model file not found, downloading {model_name}...")
        download_file(model_url, model_path)

    return model_path


class ObjectTracker:
    def __init__(
        self, similarity_threshold: float = 0.5
    ):  # Lowered threshold significantly
        self.similarity_threshold = similarity_threshold
        self.tracked_objects: Dict[str, Dict] = {}
        self.class_counters = {}  # Separate counter for each class

        # Initialize MediaPipe Image Embedder
        logger.info(
            "Initializing Object Tracker with similarity threshold: %s",
            similarity_threshold,
        )
        model_path = get_model_path("embedder")
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.ImageEmbedderOptions(
            base_options=base_options, l2_normalize=True, quantize=True
        )
        self.embedder = vision.ImageEmbedder.create_from_options(options)

    def get_embedding(self, image: np.ndarray) -> Any:
        """Get embedding for an image"""
        # Convert to RGB if needed
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
        elif image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Create MediaPipe Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)

        # Get embedding
        return self.embedder.embed(mp_image)

    def find_similar_object(
        self, embedding_result: Any, class_name: str, bbox: Any, frame_idx: int
    ) -> Tuple[str, float]:
        """Find the most similar tracked object of the same class"""
        if not self.tracked_objects:
            return None, 0.0

        best_match_id = None
        best_similarity = 0.0

        for obj_id, obj in self.tracked_objects.items():
            if obj["class"] != class_name:
                continue

            # Calculate embedding similarity only
            embedding_similarity = vision.ImageEmbedder.cosine_similarity(
                embedding_result.embeddings[0], obj["embedding"].embeddings[0]
            )

            logger.debug(f"Comparing with {obj_id}: emb={embedding_similarity:.3f}")

            if embedding_similarity > best_similarity:
                best_similarity = embedding_similarity
                best_match_id = obj_id

        if best_similarity >= self.similarity_threshold:
            logger.debug(
                f"Found similar object: {best_match_id} with similarity {best_similarity:.3f}"
            )
            return best_match_id, best_similarity

        logger.debug(
            f"No similar object found. Max similarity: {best_similarity:.3f} (threshold: {self.similarity_threshold})"
        )
        return None, best_similarity

    def update(
        self, frame_idx: int, detection: Any, embedding_result: Any, bbox: Any
    ) -> str:
        """Update tracked objects with new detection"""
        class_name = detection.categories[0].category_name
        confidence = detection.categories[0].score

        # Find similar object of the same class
        obj_id, similarity = self.find_similar_object(
            embedding_result, class_name, bbox, frame_idx
        )

        if obj_id is None:
            # New object of this class
            if class_name not in self.class_counters:
                self.class_counters[class_name] = 0
            obj_id = f"{class_name}_{self.class_counters[class_name]}"
            self.class_counters[class_name] += 1

            self.tracked_objects[obj_id] = {
                "class": class_name,
                "embedding": embedding_result,
                "first_detection": frame_idx,
                "detections": [],
            }
        else:
            logger.debug(
                f"Updating existing {class_name}: {obj_id} (similarity: {similarity:.3f})"
            )

        # Update object data
        detection_data = {
            "frame_idx": frame_idx,
            "confidence": float(confidence),
            "similarity": float(similarity),
            "bbox": {
                "x": bbox.origin_x,
                "y": bbox.origin_y,
                "width": bbox.width,
                "height": bbox.height,
            },
        }

        self.tracked_objects[obj_id]["detections"].append(detection_data)

        # Update the embedding to the latest one for better future matching
        self.tracked_objects[obj_id]["embedding"] = embedding_result

        return obj_id

    def get_tracked_objects_for_json(self) -> Dict[str, Dict]:
        """Get tracked objects without embeddings for JSON output"""
        json_objects = {}
        for obj_id, obj in self.tracked_objects.items():
            json_objects[obj_id] = {
                "class": obj["class"],
                "first_detection": obj["first_detection"],
                "detections": obj["detections"],
            }
        return json_objects


class InterruptHandler:
    def __init__(self, detector, enable_signals=True):
        self.detector = detector
        self.enable_signals = enable_signals

        if enable_signals:
            try:
                # Only set up signal handling if we're in the main thread
                import threading

                if threading.current_thread() is threading.main_thread():
                    self.original_sigint = signal.getsignal(signal.SIGINT)
                    signal.signal(signal.SIGINT, self.handle_interrupt)
                    atexit.register(self.cleanup)
                else:
                    logger.debug("Not in main thread, skipping signal handler setup")
                    self.enable_signals = False
            except Exception as e:
                logger.warning(f"Could not set up signal handler: {e}")
                self.enable_signals = False

    def handle_interrupt(self, signum, frame):
        print("\nInterrupted! Exiting gracefully...")
        sys.exit(0)

    def cleanup(self):
        if self.enable_signals:
            try:
                signal.signal(signal.SIGINT, self.original_sigint)
            except Exception as e:
                logger.warning(f"Error restoring signal handler: {e}")


class SpriteGenerator:
    def __init__(self, thumbnail_size: Tuple[int, int] = (160, 90)):
        self.thumbnail_size = thumbnail_size
        self.current_x = 0
        self.current_y = 0
        self.max_width = 1920  # Maximum width for sprite
        self.sprites = []
        self.sprite_image = None
        self.actual_height = 0  # Track actual height used

    def add_thumbnail(self, image: np.ndarray, obj_id: str, frame_idx: int) -> str:
        """Add a thumbnail to the sprite and return the fragment identifier"""
        # Resize image to thumbnail size
        thumbnail = cv2.resize(image, self.thumbnail_size)

        # Convert BGR to RGB for PIL
        thumbnail_rgb = cv2.cvtColor(thumbnail, cv2.COLOR_BGR2RGB)
        pil_thumbnail = Image.fromarray(thumbnail_rgb)

        # Check if we need to start a new row
        if self.current_x + self.thumbnail_size[0] > self.max_width:
            self.current_x = 0
            self.current_y += self.thumbnail_size[1]

        # Add thumbnail to sprite
        if self.sprite_image is None:
            # Create new sprite image with initial height
            initial_height = self.thumbnail_size[1] * 10  # Start with 10 rows
            self.sprite_image = Image.new(
                "RGB", (self.max_width, initial_height), (255, 255, 255)
            )
            self.actual_height = initial_height

        # Check if we need to expand the sprite height
        required_height = self.current_y + self.thumbnail_size[1]
        if required_height > self.actual_height:
            # Create new larger sprite
            new_height = max(self.actual_height * 2, required_height)
            new_sprite = Image.new("RGB", (self.max_width, new_height), (255, 255, 255))
            new_sprite.paste(self.sprite_image, (0, 0))
            self.sprite_image = new_sprite
            self.actual_height = new_height

        # Paste thumbnail at current position
        self.sprite_image.paste(pil_thumbnail, (self.current_x, self.current_y))

        # Create fragment identifier
        fragment_id = f"#xywh={self.current_x},{self.current_y},{self.thumbnail_size[0]},{self.thumbnail_size[1]}"

        # Store sprite info
        self.sprites.append(
            {
                "obj_id": obj_id,
                "frame_idx": frame_idx,
                "x": self.current_x,
                "y": self.current_y,
                "width": self.thumbnail_size[0],
                "height": self.thumbnail_size[1],
                "fragment_id": fragment_id,
            }
        )

        # Update position for next thumbnail
        self.current_x += self.thumbnail_size[0]

        return fragment_id

    def save_sprite(self, output_path: str) -> None:
        """Save the sprite image as a JPEG file to output_path."""
        if self.sprite_image is not None:
            # Crop the sprite to the actual used area
            actual_used_height = self.current_y + self.thumbnail_size[1]
            if actual_used_height < self.actual_height:
                self.sprite_image = self.sprite_image.crop(
                    (0, 0, self.max_width, actual_used_height)
                )
            self.sprite_image.save(output_path, format="JPEG", quality=50)
            logger.info(
                f"Sprite saved to: {output_path} (dimensions: {self.sprite_image.size})"
            )


class ObjectDetector:
    def __init__(
        self,
        min_score: float = 0.8,
        output_path: str = "detections.json",
        similarity_threshold: float = 0.2,
        external_id: str = None,
    ):
        # Initialize MediaPipe Object Detection
        model_path = get_model_path("detector")
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.ObjectDetectorOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            max_results=5,
            score_threshold=min_score,
        )
        self.detector = vision.ObjectDetector.create_from_options(options)

        # Initialize MediaPipe Face Detector
        face_model_path = get_model_path("face")
        face_base_options = python.BaseOptions(model_asset_path=face_model_path)
        face_options = vision.FaceDetectorOptions(face_base_options)
        self.face_detector = vision.FaceDetector.create_from_options(face_options)

        self.tracker = ObjectTracker(similarity_threshold)
        self.output_path = output_path
        self.external_id = external_id
        self.results = None
        self.start_time = None
        self.frame_count = 0
        self.processed_frames = 0
        self.frames_with_detections = 0
        self.last_timestamp = -1
        self.sprite_generator = None

        # Statistics tracking
        self.detection_stats = {
            "total_detections": 0,
            "person_detections": 0,
            "person_with_face": 0,
            "person_without_face": 0,
            "other_detections": 0,
            "class_counts": {},
        }

    def has_face(self, image: np.ndarray) -> bool:
        """Check if the image contains a face - used to improve person detection accuracy"""
        try:
            # Convert to RGB if needed
            if len(image.shape) == 2:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            elif image.shape[2] == 4:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
            elif image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image

            # Create MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

            # Detect faces
            detection_result = self.face_detector.detect(mp_image)

            # Return True if at least one face is detected
            has_face = len(detection_result.detections) > 0
            if has_face:
                logger.debug("Face detected in person region - confidence improved")
            return has_face

        except Exception as e:
            logger.warning(f"Error in face detection: {str(e)}")
            return False

    def process_video(
        self, video_path: str, video_source_url: str = None, progress_callback=None
    ) -> DetectionResults:
        """
        Process video and return detections in TAO JSON format
        """
        self.start_time = time.time()
        self.last_timestamp = -1

        # Create temporary directory for sprite
        import tempfile

        temp_dir = tempfile.mkdtemp(prefix="sprite_")

        # Initialize sprite generator (no path needed)
        self.sprite_generator = SpriteGenerator()

        # Open video capture
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Initialize results dictionary in TAO format
        self.results = {
            "version": get_version(),
            "metadata": {
                "video": {
                    "fps": fps,
                    "frame_count": self.frame_count,
                    "width": width,
                    "height": height,
                    "source": video_source_url if video_source_url else video_path,
                },
                "sprite": {
                    "path": "sprite.jpg",  # Just the filename, no path
                    "thumbnail_size": [160, 90],
                },
            },
            "frames": [],
        }

        # Set up interrupt handler
        import threading

        enable_signals = threading.current_thread() is threading.main_thread()
        InterruptHandler(self, enable_signals=enable_signals)

        frame_idx = 0
        consecutive_failures = 0
        max_failures = 5

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    break
                time.sleep(0.1)  # Wait a bit before retrying
                continue

            consecutive_failures = 0  # Reset on successful frame read

            try:
                # Calculate timestamp in milliseconds
                timestamp = int(frame_idx * (1000 / fps))

                # Ensure timestamp is monotonically increasing
                if timestamp <= self.last_timestamp:
                    timestamp = self.last_timestamp + 1
                self.last_timestamp = timestamp

                # Convert frame to RGB for MediaPipe
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Create MediaPipe Image
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

                # Process frame
                frame_results = self.detector.detect_for_video(mp_image, timestamp)

                if frame_results.detections:
                    self.frames_with_detections += 1
                    frame_data = {
                        "frame_idx": frame_idx,
                        "timestamp": timestamp
                        / 1000.0,  # Convert back to seconds for JSON
                        "objects": [],
                    }

                    for detection in frame_results.detections:
                        # Get bounding box
                        bbox = detection.bounding_box
                        x = int(bbox.origin_x)
                        y = int(bbox.origin_y)
                        w = int(bbox.width)
                        h = int(bbox.height)

                        # Get class and confidence
                        category = detection.categories[0]
                        class_name = category.category_name
                        confidence = category.score

                        # Track statistics
                        self.detection_stats["total_detections"] += 1
                        self.detection_stats["class_counts"][class_name] = (
                            self.detection_stats["class_counts"].get(class_name, 0) + 1
                        )

                        # Extract the detected object region
                        object_region = frame[y : y + h, x : x + w]
                        if object_region.size > 0:  # Check if region is valid
                            # For person objects, check if they contain a face to improve accuracy
                            if class_name == "person":
                                self.detection_stats["person_detections"] += 1
                                has_face = self.has_face(object_region)
                                if not has_face:
                                    self.detection_stats["person_without_face"] += 1
                                    logger.debug(
                                        f"Skipping person detection without face at frame {frame_idx}"
                                    )
                                    continue
                                else:
                                    self.detection_stats["person_with_face"] += 1
                                    # If person has face, we can be more confident in the detection
                                    # You could optionally boost confidence here
                            else:
                                self.detection_stats["other_detections"] += 1

                            # Get embedding and track object for ALL classes
                            embedding_result = self.tracker.get_embedding(object_region)
                            obj_id = self.tracker.update(
                                frame_idx, detection, embedding_result, bbox
                            )

                            # Add thumbnail to sprite and get fragment identifier
                            fragment_id = self.sprite_generator.add_thumbnail(
                                object_region, obj_id, frame_idx
                            )
                            sprite_reference = (
                                f"sprite.jpg{fragment_id}"  # Just filename + fragment
                            )

                            # Add object to frame data
                            frame_data["objects"].append(
                                {
                                    "id": obj_id,
                                    "class_name": class_name,
                                    "confidence": float(confidence),
                                    "bbox": {"x": x, "y": y, "width": w, "height": h},
                                    "thumbnail": sprite_reference,
                                }
                            )

                    # Only add frame to results if it has objects
                    if frame_data["objects"]:
                        self.results["frames"].append(frame_data)

            except Exception as e:
                logger.error(f"Error processing frame {frame_idx}: {str(e)}")
                continue

            frame_idx += 1
            self.processed_frames = frame_idx

            # Show progress percentage
            progress = (frame_idx / self.frame_count) * 100
            sys.stdout.write(f"\rProcessing: {progress:.1f}%")
            sys.stdout.flush()
            if progress_callback:
                progress_callback(progress)

        cap.release()

        # Save the sprite image to output_path
        import os

        sprite_output_path = os.path.splitext(self.output_path)[0] + ".sprite.jpg"
        self.sprite_generator.save_sprite(sprite_output_path)
        sprite_url = os.path.basename(sprite_output_path)  # Just filename

        # Calculate processing time
        end_time = time.time()
        processing_time = end_time - self.start_time

        # Update sprite path in results metadata
        self.results["metadata"]["sprite"]["path"] = sprite_output_path

        # Add processing time to results (removed images_dir field)
        self.results["metadata"]["processing"] = {
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": processing_time,
            "frames_processed": self.processed_frames,
            "frames_with_detections": self.frames_with_detections,
            "processing_speed": self.processed_frames
            / processing_time,  # frames per second
            "detection_statistics": self.detection_stats,
        }

        print(f"\nProcessing completed in {processing_time:.2f} seconds")
        print(
            f"Processed {self.processed_frames} frames, found {self.frames_with_detections} frames with detections"
        )
        print(
            f"Average processing speed: {self.processed_frames / processing_time:.2f} frames/second"
        )
        print(f"Sprite image saved in: {sprite_output_path}")
        if sprite_url != "sprite.jpg":
            print(f"Sprite URL: {sprite_url}")

        # Clean up temporary directory
        try:
            import shutil

            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            print(
                f"Warning: Failed to clean up temporary directory {temp_dir}: {str(e)}"
            )

        # Print detection statistics
        print("\nDetection Statistics:")
        print(f"  Total detections: {self.detection_stats['total_detections']}")
        print(f"  Person detections: {self.detection_stats['person_detections']}")
        print(f"    - With face: {self.detection_stats['person_with_face']}")
        print(
            f"    - Without face (filtered out): {self.detection_stats['person_without_face']}"
        )
        print(f"  Other detections: {self.detection_stats['other_detections']}")
        print("  By class:")
        for class_name, count in sorted(self.detection_stats["class_counts"].items()):
            print(f"    - {class_name}: {count}")

        return self.results


def main():
    parser = argparse.ArgumentParser(description="Process video for object detection")
    parser.add_argument("video_url", help="URL or path to the video file")
    parser.add_argument(
        "--output", "-o", help="Output JSON file path", default="detections.json"
    )
    parser.add_argument(
        "--min-score",
        "-s",
        type=float,
        help="Minimum confidence score for detections (0.0 to 1.0)",
        default=0.8,
    )
    parser.add_argument(
        "--similarity-threshold",
        "-t",
        type=float,
        help="Similarity threshold for object tracking (0.0 to 1.0)",
        default=0.5,
    )
    parser.add_argument(
        "--log-level", "-l", type=str, help="Logging level", default="INFO"
    )
    args = parser.parse_args()

    try:
        logger.info(f"Starting video processing: {args.video_url}")

        # Download video if it's a URL
        if args.video_url.startswith(("http://", "https://")):
            video_path = download_video(args.video_url)
        else:
            video_path = args.video_url

        detector = ObjectDetector(
            min_score=args.min_score,
            output_path=args.output,
            similarity_threshold=args.similarity_threshold,
        )
        results = detector.process_video(video_path, video_source_url=args.video_url)

        # Save results to JSON file
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Detection completed. Results saved to {args.output}")

        # Clean up downloaded video if it was downloaded
        if args.video_url.startswith(("http://", "https://")):
            try:
                os.remove(video_path)
                logger.info(f"Cleaned up temporary video file: {video_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary video file: {str(e)}")

    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
