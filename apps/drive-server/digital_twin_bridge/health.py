"""
Lightweight health/metrics monitor for the bridge service.

Keeps a rolling window of recent capture cycles and computes summary
statistics that can be logged or exposed via an API.
"""

import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Any

logger = logging.getLogger(__name__)

# Maximum number of cycle records to retain for rolling statistics.
_WINDOW_SIZE = 100


@dataclass
class _CycleRecord:
    """Metrics for a single capture cycle."""
    cycle_time: float
    objects_captured: int
    batch_size: int
    timestamp: float = field(default_factory=time.time)


class HealthMonitor:
    """Collects per-cycle metrics and exposes aggregate health status.

    Usage::

        health = HealthMonitor()
        # ... in your main loop ...
        health.record_cycle(cycle_time, objects_captured, batch_size)
        status = health.get_status()
    """

    def __init__(self) -> None:
        self._start_time: float = time.time()
        self._cycles: Deque[_CycleRecord] = deque(maxlen=_WINDOW_SIZE)
        self._total_captures: int = 0
        self._total_cycles: int = 0

    def record_cycle(
        self,
        cycle_time: float,
        objects_captured: int,
        batch_size: int,
    ) -> None:
        """Record the outcome of one capture cycle.

        Args:
            cycle_time: Wall-clock duration of the cycle in seconds.
            objects_captured: Number of objects successfully photographed.
            batch_size: Number of objects that were scheduled (may differ
                from *objects_captured* if some captures failed).
        """
        self._cycles.append(
            _CycleRecord(
                cycle_time=cycle_time,
                objects_captured=objects_captured,
                batch_size=batch_size,
            )
        )
        self._total_captures += objects_captured
        self._total_cycles += 1

    def get_status(self) -> Dict[str, Any]:
        """Return a dictionary of aggregated health metrics.

        Keys:

        * ``uptime_seconds`` -- seconds since the monitor was created.
        * ``total_cycles`` -- lifetime number of capture cycles.
        * ``total_captures`` -- lifetime number of successful captures.
        * ``avg_cycle_time`` -- average cycle duration over the rolling
          window (seconds), or ``0.0`` if no cycles recorded.
        * ``min_cycle_time`` -- shortest cycle in the window.
        * ``max_cycle_time`` -- longest cycle in the window.
        * ``avg_captures_per_cycle`` -- average successful captures per
          cycle over the window.
        * ``capture_success_rate`` -- fraction of scheduled objects that
          were successfully captured (over the window).
        * ``effective_fps`` -- approximate frames-per-second based on
          average cycle time (``1 / avg_cycle_time``), or ``0.0``.
        """
        now = time.time()
        uptime = now - self._start_time

        if self._cycles:
            cycle_times = [r.cycle_time for r in self._cycles]
            avg_cycle = sum(cycle_times) / len(cycle_times)
            min_cycle = min(cycle_times)
            max_cycle = max(cycle_times)
            total_captured_window = sum(r.objects_captured for r in self._cycles)
            total_batch_window = sum(r.batch_size for r in self._cycles)
            avg_captures = total_captured_window / len(self._cycles)
            success_rate = (
                total_captured_window / total_batch_window
                if total_batch_window > 0
                else 1.0
            )
            effective_fps = 1.0 / avg_cycle if avg_cycle > 0 else 0.0
        else:
            avg_cycle = 0.0
            min_cycle = 0.0
            max_cycle = 0.0
            avg_captures = 0.0
            success_rate = 1.0
            effective_fps = 0.0

        return {
            "uptime_seconds": round(uptime, 1),
            "total_cycles": self._total_cycles,
            "total_captures": self._total_captures,
            "avg_cycle_time": round(avg_cycle, 3),
            "min_cycle_time": round(min_cycle, 3),
            "max_cycle_time": round(max_cycle, 3),
            "avg_captures_per_cycle": round(avg_captures, 1),
            "capture_success_rate": round(success_rate, 3),
            "effective_fps": round(effective_fps, 2),
        }
