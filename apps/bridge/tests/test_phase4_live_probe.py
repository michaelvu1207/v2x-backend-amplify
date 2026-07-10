import json

import pytest

from tools.verify_phase4_live import (
    VerificationError,
    binary_digest,
    choose_teleport_target,
    receive_binary_frame,
    receive_json,
    replay_clock_epoch,
    session_candidate_actor_ids,
    synchronize_world,
    teleport_pose_errors,
    validate_actor_delta,
    validate_isolated_ego_roles,
    validate_session_actor_manifest,
    websocket_url,
)


class FakeLocation:
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class FakeTransform:
    def __init__(self, x, y):
        self.location = FakeLocation(x, y)


class FakeMap:
    def __init__(self, points):
        self._points = points

    def get_spawn_points(self):
        return self._points


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)

    async def recv(self):
        return next(self.messages)


def test_websocket_url_replaces_existing_path_and_query():
    assert websocket_url("wss://example.test/old?stale=1", "/twin", "control=1") == (
        "wss://example.test/twin?control=1"
    )


def test_choose_teleport_target_maximizes_clearance():
    near = FakeTransform(5.0, 0.0)
    far = FakeTransform(100.0, 100.0)
    target = choose_teleport_target(FakeMap([near, far]), [[0.0, 0.0, 0.0]])
    assert target is far


def test_choose_teleport_target_requires_safe_separation():
    with pytest.raises(RuntimeError, match="safely separated"):
        choose_teleport_target(
            FakeMap([FakeTransform(1.0, 1.0)]), [[0.0, 0.0, 0.0]]
        )


def test_role_validation_matches_drive_session_prefix():
    validate_isolated_ego_roles(["ego_vehicle_abc", "ego_vehicle_def"])


@pytest.mark.parametrize(
    "roles",
    [
        ["v2x_ego_abc", "v2x_ego_def"],
        ["ego_vehicle_same", "ego_vehicle_same"],
        ["ego_vehicle_only"],
    ],
)
def test_role_validation_rejects_wrong_or_overlapping_roles(roles):
    with pytest.raises(RuntimeError, match="not isolated"):
        validate_isolated_ego_roles(roles)


@pytest.mark.asyncio
async def test_receive_json_skips_binary_and_unrelated_messages():
    evidence = {}
    websocket = FakeWebSocket(
        [
            b"jpeg",
            "not json",
            json.dumps({"type": "telemetry"}),
            json.dumps({"type": "server_status", "active_sessions": 0}),
        ]
    )
    result = await receive_json(
        websocket, {"server_status"}, timeout=1.0, evidence=evidence
    )
    assert result["active_sessions"] == 0
    assert evidence["binary_frames"] == 1
    assert evidence["json_types"] == ["telemetry", "server_status"]


@pytest.mark.asyncio
async def test_receive_binary_frame_requires_changed_replay_content():
    evidence = {}
    baseline = binary_digest(b"live-frame")
    websocket = FakeWebSocket(
        [
            b"live-frame",
            json.dumps({"type": "twin_clock"}),
            b"replay-frame",
        ]
    )

    digest = await receive_binary_frame(
        websocket,
        timeout=1.0,
        evidence=evidence,
        different_from=baseline,
    )

    assert digest == binary_digest(b"replay-frame")
    assert evidence["binary_frames"] == 2
    assert evidence["json_types"] == ["twin_clock"]


def test_replay_clock_normalizes_live_iso_protocol_value():
    assert replay_clock_epoch("2026-07-09T22:11:12.500Z") == pytest.approx(
        1_783_635_072.5
    )
    assert replay_clock_epoch("not-a-time") is None
    assert replay_clock_epoch(float("inf")) is None


def test_actor_manifest_requires_existing_exact_disjoint_categories():
    response = {
        "vehicle_id": 10,
        "sensor_actor_ids": [11, 12],
        "scene_actor_ids": [13],
        "owned_actor_ids": [10, 11, 12, 13],
    }

    vehicle, owned, sensors, scene = validate_session_actor_manifest(
        response,
        baseline_actor_ids={1, 2},
        current_actor_ids={1, 2, 10, 11, 12, 13},
        prior_owned_actor_ids={20},
    )

    assert vehicle == 10
    assert owned == {10, 11, 12, 13}
    assert sensors == {11, 12}
    assert scene == {13}

    broken = {**response, "owned_actor_ids": [10, 11, 13]}
    with pytest.raises(VerificationError, match="exactly ego"):
        validate_session_actor_manifest(
            broken,
            baseline_actor_ids={1, 2},
            current_actor_ids={1, 2, 10, 11, 12, 13},
            prior_owned_actor_ids=set(),
        )


def test_full_actor_delta_rejects_unmanifested_or_nonexistent_actor():
    validate_actor_delta({10, 11, 12}, {10, 11, 12})
    with pytest.raises(VerificationError, match=r"undeclared=\[99\]"):
        validate_actor_delta({10, 11, 12, 99}, {10, 11, 12})
    with pytest.raises(VerificationError, match=r"missing=\[12\]"):
        validate_actor_delta({10, 11}, {10, 11, 12})


def test_actor_delta_allows_only_known_map_and_live_twin_actors():
    inventory = {
        15: {"type_id": "spectator", "role_name": ""},
        18: {"type_id": "traffic.traffic_light", "role_name": ""},
        33: {"type_id": "sensor.camera.rgb", "role_name": "twin_rig"},
        40: {"type_id": "walker.pedestrian.0001", "role_name": "twin_object"},
        41: {"type_id": "vehicle.tesla.model3", "role_name": "ego_vehicle_a"},
        42: {"type_id": "sensor.camera.rgb", "role_name": ""},
    }

    ignored = validate_actor_delta(set(inventory), {41, 42}, inventory)

    assert ignored == {15, 18, 33, 40}


@pytest.mark.parametrize(
    "identity",
    [
        {"type_id": "sensor.camera.rgb", "role_name": ""},
        {"type_id": "static.prop.trafficcone01", "role_name": ""},
        {"type_id": "vehicle.tesla.model3", "role_name": "autopilot"},
        {"type_id": "vehicle.tesla.model3", "role_name": "twin_rig"},
        {"type_id": "sensor.camera.rgb", "role_name": "twin_object"},
    ],
)
def test_actor_delta_still_rejects_possible_drive_session_leaks(identity):
    with pytest.raises(VerificationError, match=r"undeclared=\[99\]"):
        validate_actor_delta({99}, set(), {99: identity})


def test_cleanup_candidates_exclude_map_and_live_twin_churn():
    inventory = {
        15: {"type_id": "spectator", "role_name": ""},
        33: {"type_id": "sensor.camera.rgb", "role_name": "twin_rig"},
        40: {"type_id": "vehicle.audi.tt", "role_name": "twin_object"},
        41: {"type_id": "vehicle.tesla.model3", "role_name": "ego_vehicle_a"},
        42: {"type_id": "static.prop.trafficcone01", "role_name": ""},
    }

    assert session_candidate_actor_ids(set(inventory), inventory) == {41, 42}


def test_world_synchronization_requires_a_real_nonzero_snapshot():
    class Snapshot:
        frame = 1234

    class World:
        def __init__(self):
            self.timeout = None

        def wait_for_tick(self, timeout):
            self.timeout = timeout
            return Snapshot()

    world = World()
    assert synchronize_world(world, 2.5) == 1234
    assert world.timeout == 2.5


@pytest.mark.parametrize("snapshot", [None, object()])
def test_world_synchronization_rejects_missing_or_frame_zero_snapshot(snapshot):
    class World:
        def wait_for_tick(self, _timeout):
            return snapshot

    with pytest.raises(VerificationError, match="no real frame"):
        synchronize_world(World(), 1.0)


def test_teleport_pose_errors_compare_requested_target_and_wrap_yaw():
    position_error, yaw_error = teleport_pose_errors(
        [3.0, 4.0, 99.0], 179.0, [0.0, 0.0], -179.0
    )

    assert position_error == pytest.approx(5.0)
    assert yaw_error == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("position", "yaw"),
    [
        ([], 0.0),
        ([0.0, 0.0], None),
        ([float("nan"), 0.0], 0.0),
    ],
)
def test_teleport_pose_errors_reject_malformed_protocol_values(position, yaw):
    with pytest.raises(VerificationError, match="no valid pose"):
        teleport_pose_errors(position, yaw, [0.0, 0.0], 0.0)
