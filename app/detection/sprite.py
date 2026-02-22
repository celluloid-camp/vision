import logging
from typing import Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


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
