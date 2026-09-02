"""
DriveTestHarness — orchestrates a complete drive session in test.

Can run against mocked CARLA (unit) or real CARLA (integration).
This is the foundation for the E2E smoke test.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

import pytest

from tests.conftest import (
    MockClient,
    MockWorld,
    MockWebSocket,
    MockVehicleControl,
    FakeV2XApi,
    SAMPLE_DETECTIONS,
)


@dataclass
class DriveSessionResult:
    """Result of a test drive session."""
    session_ready: bool = False
    vehicle_id: Optional[int] = None
    objects_count: int = 0
    telemetry_received: int = 0
    control_messages_sent: int = 0
    controls_applied: list = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    session_ended_cleanly: bool = False
    recording_file: Optional[str] = None
    actors_remaining_after_cleanup: int = 0


class DriveTestHarness:
    """
    Orchestrates a complete drive session for testing.

    Usage::

        harness = DriveTestHarness(mock_world=world, fake_api=api)
        result = await harness.run_session(
            timeframe=("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z"),
            control_sequence=[
                {"s": 0.0, "t": 0.5, "b": 0.0},  # straight, half throttle
                {"s": -0.3, "t": 0.3, "b": 0.0},  # turn left
                {"s": 0.0, "t": 0.0, "b": 0.8},   # brake hard
            ],
            duration_per_control=0.016,  # ~60Hz
        )
        assert result.session_ready
        assert result.session_ended_cleanly
        assert result.actors_remaining_after_cleanup == 0
    """

    def __init__(
        self,
        mock_world: Optional[MockWorld] = None,
        fake_api: Optional[FakeV2XApi] = None,
    ):
        self.world = mock_world or MockWorld()
        self.api = fake_api or FakeV2XApi()
        self.ws = MockWebSocket()

    async def run_session(
        self,
        timeframe: tuple[str, str] = (
            "2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z"
        ),
        control_sequence: Optional[list[dict]] = None,
        duration_per_control: float = 0.016,
    ) -> DriveSessionResult:
        """Run a complete simulated drive session and return results."""
        result = DriveSessionResult()

        if control_sequence is None:
            control_sequence = [
                {"s": 0.0, "t": 0.5, "b": 0.0},
                {"s": -0.2, "t": 0.3, "b": 0.0},
                {"s": 0.1, "t": 0.0, "b": 0.5},
            ]

        try:
            # 1. Start session
            start_msg = json.dumps({
                "type": "start_session",
                "start": timeframe[0],
                "end": timeframe[1],
            })
            await self.ws.inject(start_msg)

            # Simulate scene reconstruction
            api_result = self.api.get_detections_range(
                timeframe[0], timeframe[1]
            )
            result.objects_count = api_result["count"]

            # Spawn vehicle
            bp_lib = self.world.get_blueprint_library()
            vehicle_bp = bp_lib.filter("vehicle.tesla.model3")[0]
            spawn_points = self.world.get_map().get_spawn_points()
            vehicle = self.world.try_spawn_actor(vehicle_bp, spawn_points[0])

            if vehicle is None:
                result.errors.append("Failed to spawn vehicle")
                return result

            result.vehicle_id = vehicle.id
            result.session_ready = True

            # Send session_ready response
            await self.ws.send(json.dumps({
                "type": "session_ready",
                "vehicle_id": vehicle.id,
                "objects_count": result.objects_count,
            }))

            # 2. Send control sequence
            for ctrl in control_sequence:
                control_msg = json.dumps({
                    "type": "control",
                    "s": ctrl["s"],
                    "t": ctrl["t"],
                    "b": ctrl["b"],
                })
                await self.ws.inject(control_msg)

                # Apply control to vehicle
                vc = MockVehicleControl(
                    steer=ctrl["s"],
                    throttle=ctrl["t"],
                    brake=ctrl["b"],
                )
                vehicle.apply_control(vc)
                result.control_messages_sent += 1
                result.controls_applied.append(ctrl)

                # Send telemetry back
                await self.ws.send(json.dumps({
                    "type": "telemetry",
                    "speed": 10.0 * ctrl["t"],
                    "gear": 1,
                    "pos": [100.0, 200.0, 0.1],
                    "rot": [0, 0, 0],
                }))
                result.telemetry_received += 1

            # 3. End session
            await self.ws.inject(json.dumps({"type": "end_session"}))
            vehicle.destroy()
            result.session_ended_cleanly = True

            # Count remaining actors (should be 0 after cleanup)
            result.actors_remaining_after_cleanup = len([
                a for a in self.world.spawned_actors if not a.is_destroyed
            ])

        except Exception as e:
            result.errors.append(str(e))

        return result


# ──────────────────────────────────────────────────────────────
# Tests for the harness itself
# ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestDriveTestHarness:
    """Verify the test harness works correctly with mocked components."""

    @pytest.mark.asyncio
    async def test_full_session_succeeds(self, mock_world, fake_v2x_api):
        harness = DriveTestHarness(mock_world=mock_world, fake_api=fake_v2x_api)
        result = await harness.run_session()

        assert result.session_ready is True
        assert result.vehicle_id is not None
        assert result.objects_count > 0
        assert result.control_messages_sent == 3
        assert result.telemetry_received == 3
        assert result.session_ended_cleanly is True
        assert result.actors_remaining_after_cleanup == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_empty_scene(self, mock_world, empty_v2x_api):
        harness = DriveTestHarness(mock_world=mock_world, fake_api=empty_v2x_api)
        result = await harness.run_session()

        assert result.session_ready is True
        assert result.objects_count == 0
        assert result.session_ended_cleanly is True

    @pytest.mark.asyncio
    async def test_control_values_applied_correctly(self, mock_world, fake_v2x_api):
        controls = [
            {"s": -1.0, "t": 1.0, "b": 0.0},  # full left, full throttle
            {"s": 1.0, "t": 0.0, "b": 1.0},    # full right, full brake
        ]
        harness = DriveTestHarness(mock_world=mock_world, fake_api=fake_v2x_api)
        result = await harness.run_session(control_sequence=controls)

        # Check vehicle received correct control values
        vehicle = mock_world.get_actor(result.vehicle_id)
        assert len(vehicle.control_history) == 2
        assert vehicle.control_history[0].steer == -1.0
        assert vehicle.control_history[0].throttle == 1.0
        assert vehicle.control_history[1].steer == 1.0
        assert vehicle.control_history[1].brake == 1.0

    @pytest.mark.asyncio
    async def test_websocket_messages_well_formed(self, mock_world, fake_v2x_api):
        harness = DriveTestHarness(mock_world=mock_world, fake_api=fake_v2x_api)
        result = await harness.run_session()

        sent = harness.ws.get_sent_json()
        # First message should be session_ready
        assert sent[0]["type"] == "session_ready"
        assert "vehicle_id" in sent[0]
        assert "objects_count" in sent[0]

        # Remaining should be telemetry
        for msg in sent[1:]:
            assert msg["type"] == "telemetry"
            assert "speed" in msg
            assert "gear" in msg
            assert "pos" in msg
            assert "rot" in msg
