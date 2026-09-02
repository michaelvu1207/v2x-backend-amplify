"""
Persistent camera pool for capturing snapshots of tracked objects.

Spawns a fixed number of CARLA RGB cameras once at startup and reuses
them across capture cycles by teleporting them to new positions.  This
avoids the overhead of spawning/destroying sensors every cycle.
"""

import logging
from queue import Queue, Empty
from typing import List, Tuple, Optional

import carla

from digital_twin_bridge.carla_connection import CarlaConnection
from digital_twin_bridge.config import Config
from digital_twin_bridge.object_registry import TrackedObject
from digital_twin_bridge.geo_utils import compute_look_at_transform
from digital_twin_bridge.frame_encoder import encode_jpeg

logger = logging.getLogger(__name__)


class CameraPool:
    """A fixed-size pool of CARLA RGB camera sensors.

    Cameras are spawned once via :meth:`spawn_cameras` and subsequently
    repositioned for each capture batch.  Call :meth:`destroy` to clean
    up when shutting down.
    """

    def __init__(self, connection: CarlaConnection, config: Config) -> None:
        self._conn = connection
        self._config = config
        self._cameras: List[carla.Actor] = []
        self._queues: List[Queue] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def spawn_cameras(self) -> None:
        """Spawn ``NUM_CAMERAS`` RGB cameras in the CARLA world.

        Each camera gets its own :class:`queue.Queue` listener.  The
        cameras are placed at the world origin initially; they will be
        teleported before the first capture.
        """
        world = self._conn.world
        bp_lib = world.get_blueprint_library()
        cam_bp = bp_lib.find("sensor.camera.rgb")
        cam_bp.set_attribute("image_size_x", str(self._config.CAM_IMAGE_WIDTH))
        cam_bp.set_attribute("image_size_y", str(self._config.CAM_IMAGE_HEIGHT))

        # Park the cameras at a harmless default location
        default_transform = carla.Transform(
            carla.Location(x=0, y=0, z=50),
            carla.Rotation(),
        )

        for i in range(self._config.NUM_CAMERAS):
            camera = world.spawn_actor(cam_bp, default_transform)
            q: Queue = Queue(maxsize=4)
            camera.listen(lambda image, _q=q: _q.put(image))
            self._cameras.append(camera)
            self._queues.append(q)
            logger.info("Spawned camera %d (id=%d).", i, camera.id)

        logger.info(
            "Camera pool ready: %d cameras at %dx%d.",
            len(self._cameras),
            self._config.CAM_IMAGE_WIDTH,
            self._config.CAM_IMAGE_HEIGHT,
        )

    def destroy(self) -> None:
        """Stop listening and destroy all cameras.

        Attempts to tick the world once before destroying so that CARLA
        can process pending commands in synchronous mode.  Errors during
        cleanup are suppressed so shutdown always completes.
        """
        # One tick so CARLA can process pending commands before we destroy
        try:
            self._conn.tick()
        except Exception:
            pass

        for i, camera in enumerate(self._cameras):
            try:
                camera.stop()
            except Exception:
                pass
            try:
                camera.destroy()
                logger.debug("Destroyed camera %d (id=%d).", i, camera.id)
            except Exception:
                logger.debug("Could not destroy camera %d (already gone).", i)
        self._cameras.clear()
        self._queues.clear()
        logger.info("Camera pool destroyed.")

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def _drain_queue(self, q: Queue) -> None:
        """Discard all frames currently sitting in a queue."""
        while not q.empty():
            try:
                q.get_nowait()
            except Empty:
                break

    def capture_batch(
        self, objects: List[TrackedObject]
    ) -> List[Tuple[TrackedObject, bytes]]:
        """Capture one JPEG snapshot per object using the camera pool.

        All cameras are teleported simultaneously, then a shared set of
        settle ticks runs once, followed by a single capture tick.  This
        is much faster than sequential per-camera capture and avoids
        queue-timing issues.

        Args:
            objects: Tracked objects to photograph.  At most
                ``len(self._cameras)`` objects will be processed.

        Returns:
            A list of ``(TrackedObject, jpeg_bytes)`` tuples for each
            successful capture.
        """
        if not self._cameras:
            logger.warning("capture_batch called but no cameras are spawned.")
            return []

        # Limit to available cameras and filter objects without locations
        batch: List[Tuple[int, TrackedObject]] = []
        for idx, obj in enumerate(objects[: len(self._cameras)]):
            if obj.carla_location is None:
                logger.warning(
                    "Object %s has no CARLA location; skipping.", obj.object_id
                )
                continue
            batch.append((idx, obj))

        if not batch:
            return []

        # 1. Teleport ALL cameras at once
        for idx, obj in batch:
            cam_transform = compute_look_at_transform(
                obj.carla_location,
                offset_distance=self._config.CAM_OFFSET_DISTANCE,
                offset_height=self._config.CAM_OFFSET_HEIGHT,
            )
            self._cameras[idx].set_transform(cam_transform)

        # 2. Drain all queues
        for idx, _ in batch:
            self._drain_queue(self._queues[idx])

        # 3. Settle ticks (shared across all cameras)
        for _ in range(self._config.SETTLE_TICKS):
            self._conn.tick()
            for idx, _ in batch:
                self._drain_queue(self._queues[idx])

        # 4. Single capture tick
        self._conn.tick()

        # 5. Retrieve frames from all cameras
        results: List[Tuple[TrackedObject, bytes]] = []
        for idx, obj in batch:
            try:
                image = self._queues[idx].get(timeout=5.0)
            except Empty:
                logger.warning(
                    "Timeout waiting for frame from camera %d for object %s.",
                    idx,
                    obj.object_id,
                )
                continue

            try:
                jpeg_bytes = encode_jpeg(image, quality=self._config.JPEG_QUALITY)
            except Exception:
                logger.error(
                    "Failed to encode JPEG for object %s.",
                    obj.object_id,
                    exc_info=True,
                )
                continue

            results.append((obj, jpeg_bytes))
            logger.debug(
                "Captured object %s (%s) -- %d bytes.",
                obj.object_id,
                obj.object_type,
                len(jpeg_bytes),
            )

        logger.info(
            "Batch capture complete: %d/%d successful.", len(results), len(batch)
        )
        return results

    @property
    def size(self) -> int:
        """Number of cameras in the pool."""
        return len(self._cameras)
