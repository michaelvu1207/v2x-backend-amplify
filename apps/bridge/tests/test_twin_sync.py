"""Tests for TwinSync: detections -> CARLA actor lifecycle."""

import time

import pytest

from digital_twin_bridge import twin_sync as twin_sync_module
from digital_twin_bridge.twin_sync import TwinSync

from tests.conftest import MockBlueprint, MockLocation


def make_detection(object_id="global_car_1", object_type="car", lat=37.9155, lon=-122.3348):
    return {
        "object_id": object_id,
        "object_type": object_type,
        "confidence_score": 0.9,
        "gps_location": {"latitude": lat, "longitude": lon},
    }


@pytest.fixture
def sync(mock_world, monkeypatch):
    # GPS -> CARLA: deterministic linear mapping so movement is observable.
    monkeypatch.setattr(
        twin_sync_module,
        "gps_to_carla",
        lambda m, lat, lon: MockLocation((lat - 37.9) * 1000.0, (lon + 122.3) * 1000.0, 0.0),
    )
    # The default MockBlueprintLibrary.filter does substring matching that
    # misses "vehicle.*"; substitute wildcard-aware pools.
    pools = {
        "vehicle.*": [MockBlueprint("vehicle.tesla.model3"), MockBlueprint("vehicle.ford.truck")],
        "walker.pedestrian.*": [MockBlueprint("walker.pedestrian.0001")],
    }
    mock_world._blueprint_library.filter = lambda pattern: list(pools.get(pattern, []))
    return TwinSync(mock_world, mock_world.get_map(), poll_interval=1.0, despawn_after=12.0)


class TestSpawn:
    def test_car_detection_spawns_vehicle(self, sync, mock_world):
        sync._apply([make_detection()])
        assert len(sync.actor_ids()) == 1
        actor = mock_world.get_actor(next(iter(sync.actor_ids())))
        assert actor.type_id.startswith("vehicle.")
        assert actor.physics_enabled is False

    def test_person_detection_spawns_walker(self, sync, mock_world):
        sync._apply([make_detection(object_id="global_person_1", object_type="person")])
        actor = mock_world.get_actor(next(iter(sync.actor_ids())))
        assert actor.type_id.startswith("walker.")

    def test_track_keeps_stable_blueprint_and_actor(self, sync):
        sync._apply([make_detection()])
        first_ids = sync.actor_ids()
        sync._apply([make_detection(lat=37.9156)])
        assert sync.actor_ids() == first_ids

    def test_unknown_types_and_missing_gps_ignored(self, sync):
        sync._apply([
            make_detection(object_type="traffic light"),
            {"object_id": "x", "object_type": "car"},  # no gps_location
            {"object_type": "car", "gps_location": {"latitude": 1, "longitude": 2}},  # no id
        ])
        assert sync.actor_ids() == set()

    def test_firetruck_never_selected(self, sync, mock_world):
        pools = {
            "vehicle.*": [
                MockBlueprint("vehicle.carlamotors.firetruck"),
                MockBlueprint("vehicle.tesla.model3"),
            ],
            "walker.pedestrian.*": [],
        }
        mock_world._blueprint_library.filter = lambda pattern: list(pools.get(pattern, []))
        for i in range(8):
            sync._apply([make_detection(object_id=f"global_car_{i}")])
        for actor_id in sync.actor_ids():
            assert "firetruck" not in mock_world.get_actor(actor_id).type_id


class TestLifecycle:
    def test_stale_track_despawns(self, sync, mock_world):
        sync._apply([make_detection()])
        actor_id = next(iter(sync.actor_ids()))
        track = sync._tracks["global_car_1"]
        track.last_seen = time.time() - 20.0
        sync._despawn_stale(time.time())
        assert sync.actor_ids() == set()
        assert mock_world.get_actor(actor_id).is_destroyed

    def test_fresh_track_survives_despawn_pass(self, sync):
        sync._apply([make_detection()])
        sync._despawn_stale(time.time())
        assert len(sync.actor_ids()) == 1

    def test_stop_destroys_everything(self, sync, mock_world):
        sync._apply([make_detection(), make_detection(object_id="global_car_2")])
        actor_ids = set(sync.actor_ids())
        sync.stop()
        assert sync.actor_ids() == set()
        for actor_id in actor_ids:
            assert mock_world.get_actor(actor_id).is_destroyed


class TestTick:
    def test_tick_lerps_towards_new_fix(self, sync, mock_world):
        sync._apply([make_detection(lat=37.9155)])
        actor_id = next(iter(sync.actor_ids()))
        track = sync._tracks["global_car_1"]

        # New fix ~11m north; pretend the poll happened 0.5s ago (mid-lerp).
        sync._apply([make_detection(lat=37.9156)])
        track.lerp_start = time.time() - 0.5
        sync.tick()

        actor = mock_world.get_actor(actor_id)
        x = actor.get_transform().location.x
        assert track.current.x < x <= track.target.x

        # Once the lerp window has fully elapsed, we land on the target.
        track.lerp_start = time.time() - 5.0
        sync.tick()
        assert actor.get_transform().location.x == pytest.approx(track.target.x)

    def test_tick_handles_vanished_actor(self, sync, mock_world):
        sync._apply([make_detection()])
        track = sync._tracks["global_car_1"]
        mock_world._actors.clear()
        sync.tick()
        assert track.actor_id is None


class TestFetchParsing:
    def test_flattens_cameras_and_skips_stale(self, sync, monkeypatch):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        fresh = (now - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        stale = (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        payload = {
            "cameras": {
                "ch1": {"updated_at": fresh, "detections": [make_detection()]},
                "ch2": {"updated_at": stale, "detections": [make_detection(object_id="old")]},
            }
        }

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return payload

        monkeypatch.setattr(
            twin_sync_module.requests, "get", lambda url, timeout=5: FakeResponse()
        )
        detections = sync._fetch_detections()
        assert [d["object_id"] for d in detections] == ["global_car_1"]
