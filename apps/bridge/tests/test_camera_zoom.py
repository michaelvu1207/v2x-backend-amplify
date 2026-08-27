"""Tests for bird's-eye camera zoom (altitude dolly via camera_zoom messages)."""

import pytest


async def _bird_session(mock_world, fake_v2x_api):
    from digital_twin_bridge.drive_server import DriveSession

    session = DriveSession(
        world=mock_world,
        carla_map=mock_world.get_map(),
        api_fetcher=fake_v2x_api.get_detections_range,
    )
    await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")
    session.switch_camera("bird")
    return session


@pytest.mark.unit
class TestCameraZoom:
    """Unit tests for DriveSession.zoom_camera with mocked CARLA."""

    @pytest.mark.asyncio
    async def test_zoom_out_scales_altitude(self, mock_world, fake_v2x_api):
        """A factor > 1 climbs the camera multiplicatively and acks the result."""
        from digital_twin_bridge.drive_server import BIRD_ZOOM_DEFAULT_ALTITUDE_M

        session = await _bird_session(mock_world, fake_v2x_api)

        response = session.zoom_camera(factor=1.15)

        assert response["type"] == "camera_zoomed"
        expected = BIRD_ZOOM_DEFAULT_ALTITUDE_M * 1.15
        assert response["altitude"] == pytest.approx(expected, abs=0.01)
        assert session._bird_altitude == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_zoom_applies_in_place_without_respawn(self, mock_world, fake_v2x_api):
        """Zoom must move the live sensor via set_location, not respawn it."""
        session = await _bird_session(mock_world, fake_v2x_api)
        sensor = session._camera_sensor
        assert sensor is not None

        session.zoom_camera(factor=1.5)

        assert not sensor.is_destroyed
        assert session._camera_sensor is sensor
        assert len(sensor.set_location_calls) == 1
        assert sensor.set_location_calls[-1].z == pytest.approx(session._bird_altitude)

    @pytest.mark.asyncio
    async def test_zoom_clamps_at_max_altitude(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import BIRD_ZOOM_MAX_ALTITUDE_M

        session = await _bird_session(mock_world, fake_v2x_api)

        for _ in range(10):
            response = session.zoom_camera(factor=5.0)

        assert response["altitude"] == BIRD_ZOOM_MAX_ALTITUDE_M
        assert session._bird_altitude == BIRD_ZOOM_MAX_ALTITUDE_M

    @pytest.mark.asyncio
    async def test_zoom_clamps_at_min_altitude(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import BIRD_ZOOM_MIN_ALTITUDE_M

        session = await _bird_session(mock_world, fake_v2x_api)

        for _ in range(10):
            response = session.zoom_camera(factor=0.2)

        assert response["altitude"] == BIRD_ZOOM_MIN_ALTITUDE_M

    @pytest.mark.asyncio
    async def test_zoom_reset_restores_default(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import BIRD_ZOOM_DEFAULT_ALTITUDE_M

        session = await _bird_session(mock_world, fake_v2x_api)
        session.zoom_camera(factor=2.0)

        response = session.zoom_camera(reset=True)

        assert response["altitude"] == BIRD_ZOOM_DEFAULT_ALTITUDE_M
        assert session._bird_altitude == BIRD_ZOOM_DEFAULT_ALTITUDE_M

    @pytest.mark.asyncio
    async def test_zoom_persists_across_view_switches(self, mock_world, fake_v2x_api):
        """The zoomed altitude survives leaving and re-entering bird view."""
        session = await _bird_session(mock_world, fake_v2x_api)
        session.zoom_camera(factor=2.0)
        zoomed = session._bird_altitude

        session.switch_camera("hood")
        session.switch_camera("bird")

        assert session._bird_altitude == zoomed
        assert session._transform_for_view("bird").location.z == pytest.approx(zoomed)

    @pytest.mark.asyncio
    async def test_zoom_outside_bird_view_stores_without_moving_sensor(
        self, mock_world, fake_v2x_api
    ):
        """In other views the altitude is stored for later but nothing moves."""
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")
        assert session.active_camera == "chase"
        sensor = session._camera_sensor

        response = session.zoom_camera(factor=2.0)

        assert response["type"] == "camera_zoomed"
        assert sensor.set_location_calls == []

    @pytest.mark.asyncio
    async def test_invalid_zoom_factor_raises(self, mock_world, fake_v2x_api):
        session = await _bird_session(mock_world, fake_v2x_api)

        for bad in (0.0, -1.0, 100.0, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                session.zoom_camera(factor=bad)


@pytest.mark.unit
class TestCameraZoomMessageHandling:
    """Protocol-level tests through handle_message."""

    @pytest.mark.asyncio
    async def test_handle_camera_zoom(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import (
            BIRD_ZOOM_MAX_ALTITUDE_M,
            BIRD_ZOOM_MIN_ALTITUDE_M,
            handle_message,
        )

        session = await _bird_session(mock_world, fake_v2x_api)

        response = await handle_message(session, {"type": "camera_zoom", "factor": 1.15})

        assert response["type"] == "camera_zoomed"
        assert response["min"] == BIRD_ZOOM_MIN_ALTITUDE_M
        assert response["max"] == BIRD_ZOOM_MAX_ALTITUDE_M

    @pytest.mark.asyncio
    async def test_handle_camera_zoom_reset(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import (
            BIRD_ZOOM_DEFAULT_ALTITUDE_M,
            handle_message,
        )

        session = await _bird_session(mock_world, fake_v2x_api)
        session.zoom_camera(factor=3.0)

        response = await handle_message(session, {"type": "camera_zoom", "reset": True})

        assert response["altitude"] == BIRD_ZOOM_DEFAULT_ALTITUDE_M

    @pytest.mark.asyncio
    async def test_handle_camera_zoom_invalid_factor_returns_error(
        self, mock_world, fake_v2x_api
    ):
        from digital_twin_bridge.drive_server import handle_message

        session = await _bird_session(mock_world, fake_v2x_api)

        for bad in (100.0, 0.0, "abc"):
            response = await handle_message(
                session, {"type": "camera_zoom", "factor": bad}
            )
            assert response["type"] == "error"
