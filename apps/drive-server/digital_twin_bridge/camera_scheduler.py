"""
Priority-based scheduler for camera assignments.

Decides which tracked objects should get camera time next based on how
long ago they were last photographed, how recently they were detected,
and their detection confidence.
"""

import time
import logging
from datetime import datetime, timezone
from typing import List

from digital_twin_bridge.object_registry import ObjectRegistry, TrackedObject

logger = logging.getLogger(__name__)

# Objects that have never been captured receive this synthetic
# "seconds since last capture" value to ensure they are prioritised.
_NEVER_CAPTURED_BOOST = 1_000_000.0

# Maximum age (seconds) of a V2X timestamp before recency weight decays
# to its minimum.  Detections older than this still get a small weight.
_RECENCY_HALF_LIFE = 60.0  # seconds


class CameraScheduler:
    """Assigns camera time-slots to tracked objects using a priority score.

    Priority score formula::

        score = time_since_last_capture * recency_weight * confidence_weight

    * **time_since_last_capture** -- seconds since the last photo was taken
      of this object.  Objects that have *never* been captured are given an
      artificially high value.
    * **recency_weight** -- a boost for objects whose V2X detection
      timestamp is recent.  Computed as ``2^(-age / half_life)`` so newer
      detections score higher.
    * **confidence_weight** -- the raw detection confidence (0-1); higher
      confidence means higher priority.
    """

    def __init__(self, registry: ObjectRegistry) -> None:
        self._registry = registry

    def _priority_score(self, obj: TrackedObject) -> float:
        """Compute the scheduling priority for a single object."""
        now = time.time()

        # Time since last capture
        if obj.last_captured <= 0:
            time_since_capture = _NEVER_CAPTURED_BOOST
        else:
            time_since_capture = max(now - obj.last_captured, 0.01)

        # Recency weight based on the V2X detection timestamp
        recency_weight = 1.0
        if obj.timestamp_utc:
            try:
                dt = datetime.fromisoformat(
                    obj.timestamp_utc.replace("Z", "+00:00")
                )
                detection_age = (
                    datetime.now(timezone.utc) - dt
                ).total_seconds()
                detection_age = max(detection_age, 0.0)
                recency_weight = 2.0 ** (-detection_age / _RECENCY_HALF_LIFE)
                # Floor so stale detections still get some weight
                recency_weight = max(recency_weight, 0.05)
            except (ValueError, TypeError):
                recency_weight = 0.5

        # Confidence weight (clamp to [0.01, 1.0])
        confidence_weight = max(min(obj.confidence, 1.0), 0.01)

        return time_since_capture * recency_weight * confidence_weight

    def next_batch(self, batch_size: int) -> List[TrackedObject]:
        """Return the top *batch_size* objects ranked by priority.

        If fewer objects are available than *batch_size*, all available
        objects are returned.

        Args:
            batch_size: Maximum number of objects to return.

        Returns:
            A list of :class:`TrackedObject` instances sorted by
            descending priority (highest priority first).
        """
        objects = self._registry.get_all()
        if not objects:
            return []

        # Filter out objects without a resolved CARLA location -- we
        # cannot point a camera at them.
        locatable = [o for o in objects if o.carla_location is not None]
        if not locatable:
            logger.debug(
                "No objects with CARLA locations available for scheduling."
            )
            return []

        scored = sorted(
            locatable, key=self._priority_score, reverse=True
        )
        batch = scored[:batch_size]

        if batch:
            logger.debug(
                "Scheduled %d objects (top score %.1f, bottom %.1f).",
                len(batch),
                self._priority_score(batch[0]),
                self._priority_score(batch[-1]),
            )

        return batch
