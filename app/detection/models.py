import logging
import os

from app.core.utils import download_file, ensure_dir

logger = logging.getLogger(__name__)


def get_model_path(model_type: str = "detector") -> str:
    """
    Get the path to the model file, downloading it if necessary.
    """
    # if model_type == "detector":
    #     model_url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite"
    #     model_name = "efficientdet_lite2.tflite"
    # elif model_type == "embedder":
    #     model_url = "https://storage.googleapis.com/mediapipe-models/image_embedder/mobilenet_v3_large/float32/latest/mobilenet_v3_large.tflite"
    #     model_name = "mobilenet_v3_large.tflite"
    if model_type == "detector":
        model_url = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite"
        model_name = "efficientdet_lite0.tflite"
    elif model_type == "embedder":
        model_url = "https://storage.googleapis.com/mediapipe-models/image_embedder/mobilenet_v3_small/float32/latest/mobilenet_v3_small.tflite"
        model_name = "mobilenet_v3_small.tflite"

    elif model_type == "face":
        model_url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
        model_name = "detector.tflite"
    else:
        raise ValueError(f"Unsupported model type: {model_type}")

    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    ensure_dir(model_dir)
    model_path = os.path.join(model_dir, model_name)

    if not os.path.exists(model_path):
        logger.info("Model file not found, downloading %s...", model_name)
        download_file(model_url, model_path)

    return model_path
