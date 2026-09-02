"""Tests for Camera Streamer — validates camera transforms and frame handling."""

import math
import pytest
from tests.conftest import MockWorld, MockActor, MockTransform, MockLocation, MockRotation


@pytest.mark.unit
class TestCameraTransforms:
    """Test camera view transform calculations."""

    def test_chase_camera_behind_vehicle(self):
        """Chase cam should be behind and above the vehicle."""
        from digital_twin_bridge.camera_streamer import compute_camera_transform

        vehicle_transform = MockTransform(
            MockLocation(100, 200, 0),
            MockRotation(0, 0, 0),  # facing +X
        )
        cam = compute_camera_transform("chase", vehicle_transform)

        # Should be behind (-X direction) and above (+Z)
        assert cam.location.x < vehicle_transform.location.x  # behind
        assert cam.location.z > vehicle_transform.location.z  # above
        assert cam.rotation.pitch < 0  # looking down

    def test_hood_camera_on_vehicle(self):
        """Hood cam should be at driver eye position."""
        from digital_twin_bridge.camera_streamer import compute_camera_transform

        vehicle_transform = MockTransform(
            MockLocation(100, 200, 0),
            MockRotation(0, 0, 0),
        )
        cam = compute_camera_transform("hood", vehicle_transform)

        # Should be slightly ahead and above
        assert cam.location.x >= vehicle_transform.location.x
        assert cam.location.z > vehicle_transform.location.z
        assert abs(cam.rotation.pitch) < 5  # roughly level

    def test_bird_camera_above(self):
        """Bird's eye should be directly above, looking straight down."""
        from digital_twin_bridge.camera_streamer import compute_camera_transform

        vehicle_transform = MockTransform(
            MockLocation(100, 200, 0),
            MockRotation(0, 0, 0),
        )
        cam = compute_camera_transform("bird", vehicle_transform)

        assert cam.location.z > 20  # high above
        assert cam.rotation.pitch == -90  # straight down

    def test_free_camera_default(self):
        """Free cam should have a default position."""
        from digital_twin_bridge.camera_streamer import compute_camera_transform

        vehicle_transform = MockTransform(
            MockLocation(100, 200, 0),
            MockRotation(0, 0, 0),
        )
        cam = compute_camera_transform("free", vehicle_transform)
        assert cam is not None

    def test_camera_follows_vehicle_rotation(self):
        """Camera should rotate with the vehicle yaw."""
        from digital_twin_bridge.camera_streamer import compute_camera_transform

        # Vehicle facing +Y (yaw=90)
        vehicle_transform = MockTransform(
            MockLocation(100, 200, 0),
            MockRotation(0, 90, 0),
        )
        cam = compute_camera_transform("chase", vehicle_transform)

        # Chase cam should be behind in -Y direction (since vehicle faces +Y)
        assert cam.location.y < vehicle_transform.location.y

    def test_invalid_view_raises(self):
        """Invalid camera view should raise ValueError."""
        from digital_twin_bridge.camera_streamer import compute_camera_transform

        with pytest.raises(ValueError):
            compute_camera_transform("nonexistent", MockTransform())


@pytest.mark.unit
class TestFrameEncoder:
    """Test JPEG frame encoding."""

    def test_encode_numpy_array(self):
        """Should encode a numpy array to JPEG bytes."""
        from digital_twin_bridge.camera_streamer import encode_frame_jpeg
        import numpy as np

        # Create a fake 640x480 RGB image
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[100:200, 100:200] = [255, 0, 0]  # red square

        jpeg_bytes = encode_frame_jpeg(frame, quality=85)

        assert isinstance(jpeg_bytes, bytes)
        assert len(jpeg_bytes) > 0
        # JPEG magic bytes
        assert jpeg_bytes[:2] == b"\xff\xd8"
