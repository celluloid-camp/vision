import logging
from typing import Any, Dict, Tuple

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from app.detection.models import get_model_path

logger = logging.getLogger(__name__)


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
