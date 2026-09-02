"""
Regression tests for the camera respawn fix in DriveSession.set_camera_settings.

Pre-fix bug: set_camera_settings captured the camera sensor's WORLD-SPACE
transform via get_transform() and passed it to spawn_actor with
attach_to=vehicle. attach_to makes the transform vehicle-relative, so
the world coords got interpreted as a giant offset from the car and the
camera drifted further from the vehicle on every aspect-ratio / FOV click.

Post-fix: use _transform_for_view(active_camera) — the configured
local-frame transform for the active view — so every respawn snaps
the camera back to the correct vehicle-relative offset.

These tests are intentionally separate from the main test file so they
can be removed independently if no longer needed.
"""

import pytest

from tests.conftest import MockTransform, MockLocation, MockRotation


@pytest.mark.unit
class TestCameraRespawnUsesLocalTransform:
    """set_camera_settings must use _transform_for_view, not get_transform."""

    @pytest.mark.asyncio
    async def test_respawn_uses_local_transform_not_world(
        self, mock_world, fake_v2x_api
    ):
        """Respawn after set_camera_settings should use the configured
        local-frame view transform, NOT the prior camera's world transform.
        """
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")

        # The session starts in chase view by default; capture the
        # expected local-frame transform.
        expected_local = session._transform_for_view(session.active_camera)
        expected_loc = expected_local.location

        # Sanity: the initial camera was spawned at the local offset.
        original_camera = session._camera_sensor
        assert original_camera is not None
        assert original_camera._transform.location.x == pytest.approx(
            expected_loc.x, abs=1e-3
        )
        assert original_camera._transform.location.y == pytest.approx(
            expected_loc.y, abs=1e-3
        )
        assert original_camera._transform.location.z == pytest.approx(
            expected_loc.z, abs=1e-3
        )

        # Simulate the camera having drifted in the world — pre-fix this
        # is exactly what get_transform() would return after the vehicle
        # moved, and exactly what the buggy code would feed back into
        # spawn_actor as a vehicle-relative offset.
        original_camera._transform = MockTransform(
            location=MockLocation(x=12345.0, y=67890.0, z=42.0),
            rotation=MockRotation(yaw=180.0),
        )

        # Respawn with new resolution. Active view is still chase.
        result = session.set_camera_settings(
            {"image_size_x": 1280, "image_size_y": 720}
        )
        assert result["type"] == "camera_settings_set"

        # The new camera must be at the chase local offset, NOT at the
        # runaway world coords we planted on the prior sensor.
        new_camera = session._camera_sensor
        assert new_camera is not None
        assert new_camera is not original_camera

        loc = new_camera._transform.location
        assert loc.x == pytest.approx(expected_loc.x, abs=1e-3), (
            f"Respawn drifted: x={loc.x} expected {expected_loc.x} "
            f"(world-space leak — the bug is back)"
        )
        assert loc.y == pytest.approx(expected_loc.y, abs=1e-3)
        assert loc.z == pytest.approx(expected_loc.z, abs=1e-3)
        assert abs(loc.x - 12345.0) > 1.0, (
            "World-space x leaked into vehicle-relative offset"
        )

    @pytest.mark.asyncio
    async def test_repeated_respawn_does_not_drift(
        self, mock_world, fake_v2x_api
    ):
        """Calling set_camera_settings many times in a row must not
        accumulate position drift, regardless of intervening world motion.
        """
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")

        expected = session._transform_for_view(session.active_camera).location

        # Simulate 5 aspect-ratio clicks, each time with the camera
        # pretending to have drifted to a different world position.
        fake_world_positions = [
            (100.0, 200.0, 5.0),
            (500.0, -300.0, 7.0),
            (1000.0, 4000.0, 10.0),
            (-2000.0, 7000.0, 3.0),
            (50000.0, 50000.0, 50.0),
        ]
        for (wx, wy, wz) in fake_world_positions:
            session._camera_sensor._transform = MockTransform(
                location=MockLocation(x=wx, y=wy, z=wz)
            )
            session.set_camera_settings(
                {"image_size_x": 1280, "image_size_y": 720}
            )

            loc = session._camera_sensor._transform.location
            assert loc.x == pytest.approx(expected.x, abs=1e-3), (
                f"After fake-world ({wx},{wy},{wz}), respawn drifted to x={loc.x}"
            )
            assert loc.y == pytest.approx(expected.y, abs=1e-3)
            assert loc.z == pytest.approx(expected.z, abs=1e-3)

    @pytest.mark.asyncio
    async def test_respawn_uses_active_view_after_switch(
        self, mock_world, fake_v2x_api
    ):
        """After switching to hood view, set_camera_settings must use the
        hood local transform — not chase, not world coords.
        """
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")

        session.switch_camera("hood")
        hood_expected = session._transform_for_view("hood").location

        session.set_camera_settings(
            {"image_size_x": 1920, "image_size_y": 1080}
        )

        loc = session._camera_sensor._transform.location
        assert loc.x == pytest.approx(hood_expected.x, abs=1e-3)
        assert loc.y == pytest.approx(hood_expected.y, abs=1e-3)
        assert loc.z == pytest.approx(hood_expected.z, abs=1e-3)
