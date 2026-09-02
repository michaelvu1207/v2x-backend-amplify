"""
JPEG encoding utilities for CARLA camera frames.

Converts raw BGRA pixel data (from CARLA's sensor callback) into
compressed JPEG bytes suitable for upload or local storage.
"""

import io
import logging
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def encode_jpeg(carla_image, quality: int = 92) -> bytes:
    """Encode a CARLA sensor image as JPEG.

    Args:
        carla_image: A ``carla.Image`` object received from a camera
            sensor callback.  Its ``raw_data`` buffer is interpreted as
            BGRA uint8.
        quality: JPEG compression quality (1--95, higher is better).

    Returns:
        Compressed JPEG bytes.
    """
    array_bgra = np.frombuffer(carla_image.raw_data, dtype=np.uint8)
    array_bgra = array_bgra.reshape((carla_image.height, carla_image.width, 4))
    return encode_jpeg_from_numpy(array_bgra, quality=quality)


def encode_jpeg_from_numpy(
    array_bgra: np.ndarray, quality: int = 92
) -> bytes:
    """Encode a BGRA numpy array as JPEG.

    Args:
        array_bgra: A ``(H, W, 4)`` uint8 array in BGRA channel order
            (as produced by CARLA's raw frame buffer).
        quality: JPEG compression quality (1--95).

    Returns:
        Compressed JPEG bytes.
    """
    # BGRA -> RGB: drop alpha channel and reverse BGR to RGB
    array_rgb = array_bgra[:, :, :3][:, :, ::-1]

    img = Image.fromarray(array_rgb, mode="RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    jpeg_bytes = buf.getvalue()

    logger.debug(
        "Encoded JPEG: %dx%d -> %d bytes (quality=%d).",
        array_bgra.shape[1],
        array_bgra.shape[0],
        len(jpeg_bytes),
        quality,
    )
    return jpeg_bytes
