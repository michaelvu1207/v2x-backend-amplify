"""
Session Recorder — records driving session data to JSONL files.

Each session creates a file: sessions/{session_id}.jsonl
Format: one JSON object per line (metadata header, then frames, then footer).
"""

import json
import logging
import os
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


class SessionRecorder:
    """Records driving session telemetry to a JSONL file."""

    def __init__(self, session_dir: str = "sessions"):
        self._session_dir = session_dir
        self._session_id: Optional[str] = None
        self._file = None
        self._frame_count = 0
        self._start_time: float = 0.0

    def start(
        self,
        scene_start: str,
        scene_end: str,
        objects_count: int,
    ) -> str:
        """Start recording a new session. Returns the session_id."""
        os.makedirs(self._session_dir, exist_ok=True)

        self._session_id = f"drive_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        filepath = os.path.join(self._session_dir, f"{self._session_id}.jsonl")

        self._file = open(filepath, "w")
        self._frame_count = 0
        self._start_time = time.time()

        # Write metadata header
        metadata = {
            "type": "metadata",
            "session_id": self._session_id,
            "scene_start": scene_start,
            "scene_end": scene_end,
            "objects_count": objects_count,
            "recording_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._file.write(json.dumps(metadata) + "\n")
        self._file.flush()

        logger.info("Session recording started: %s", self._session_id)
        return self._session_id

    def record_frame(
        self,
        steer: float,
        throttle: float,
        brake: float,
        pos: list[float],
        rot: list[float],
        speed_kmh: float,
    ) -> None:
        """Record a single frame of driving data."""
        if self._file is None:
            raise RuntimeError("No active recording — call start() first")

        frame = {
            "t": time.time(),
            "steer": round(steer, 4),
            "throttle": round(throttle, 4),
            "brake": round(brake, 4),
            "pos": [round(v, 3) for v in pos],
            "rot": [round(v, 3) for v in rot],
            "speed_kmh": round(speed_kmh, 1),
        }
        self._file.write(json.dumps(frame) + "\n")
        self._frame_count += 1
        self._file.flush()

    def stop(self) -> dict:
        """Stop recording and return a summary."""
        duration = time.time() - self._start_time if self._start_time else 0.0

        summary = {
            "session_id": self._session_id,
            "frames_recorded": self._frame_count,
            "duration_seconds": round(duration, 2),
        }

        if self._file is not None:
            footer = {"type": "footer", **summary}
            self._file.write(json.dumps(footer) + "\n")
            self._file.close()
            self._file = None

        logger.info(
            "Session recording stopped: %s (%d frames, %.1fs)",
            self._session_id, self._frame_count, duration,
        )

        self._session_id = None
        self._frame_count = 0
        self._start_time = 0.0

        return summary

    @property
    def is_recording(self) -> bool:
        return self._file is not None
