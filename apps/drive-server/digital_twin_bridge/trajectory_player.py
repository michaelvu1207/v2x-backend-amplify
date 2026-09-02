"""
Trajectory Player — replays a recorded GPS path as a physics-driven car.

Loads a list of (timestamp, lat, lon) waypoints (in V2X detection format
or a simplified [{t, lat, lon}] format), spawns a CARLA vehicle, and each
tick applies pure-pursuit steering + PID throttle/brake so the car tracks
the path while honouring the original timestamps. The vehicle keeps full
physics — wheels roll, suspension reacts, collisions are real — at the
cost of small lateral/temporal drift on tight corners.
"""

import json
import logging
import math
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import carla

from digital_twin_bridge.geo_utils import gps_to_carla

logger = logging.getLogger(__name__)


# ── Trajectory model ────────────────────────────────────────────────────


@dataclass
class Waypoint:
    t: float                  # seconds since trajectory start
    location: carla.Location  # world coords (post GPS→CARLA, snapped to road)


@dataclass
class Trajectory:
    name: str
    waypoints: list[Waypoint]
    object_type: str = "car"

    @property
    def duration(self) -> float:
        if len(self.waypoints) < 2:
            return 0.0
        return self.waypoints[-1].t - self.waypoints[0].t


def _parse_iso_timestamp(s: str) -> float:
    """Parse '2026-04-12T05:26:00.642Z' → epoch seconds (float)."""
    s = s.strip().replace("Z", "+00:00")
    fmt = "%Y-%m-%dT%H:%M:%S.%f%z" if "." in s else "%Y-%m-%dT%H:%M:%S%z"
    return datetime.strptime(s, fmt).timestamp()


def parse_trajectory(name: str, raw: object, carla_map: carla.Map) -> Trajectory:
    """Build a Trajectory from raw JSON.

    Two input shapes are accepted:
    - V2X detection list: ``[{object_id, timestamp_utc, gps_location: {latitude, longitude}}, ...]``
      The most-frequent ``object_id`` is selected so a single trajectory falls
      out of a multi-object detection log.
    - Simple waypoint list: ``[{t, lat, lon}, ...]`` where ``t`` is seconds
      since start.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("Trajectory JSON must be a non-empty list")

    first = raw[0]
    if not isinstance(first, dict):
        raise ValueError("Trajectory entries must be objects")

    # Detect format
    if "gps_location" in first or "timestamp_utc" in first:
        return _parse_v2x_format(name, raw, carla_map)
    if "lat" in first and "lon" in first:
        return _parse_simple_format(name, raw, carla_map)
    raise ValueError("Unrecognised trajectory format")


def _parse_v2x_format(name: str, raw: list[dict], carla_map: carla.Map) -> Trajectory:
    obj_counts = Counter(r.get("object_id", "?") for r in raw)
    target_obj, _ = obj_counts.most_common(1)[0]
    records = [r for r in raw if r.get("object_id") == target_obj]
    records.sort(key=lambda r: r.get("timestamp_utc", ""))

    waypoints: list[Waypoint] = []
    t0: Optional[float] = None
    for r in records:
        gps = r.get("gps_location") or {}
        lat, lon = gps.get("latitude"), gps.get("longitude")
        ts = r.get("timestamp_utc")
        if lat is None or lon is None or ts is None:
            continue
        try:
            t = _parse_iso_timestamp(ts)
        except Exception as e:
            logger.debug("Skipping bad timestamp %r: %s", ts, e)
            continue
        if t0 is None:
            t0 = t
        loc = gps_to_carla(carla_map, float(lat), float(lon))
        waypoints.append(Waypoint(t=t - t0, location=loc))

    if len(waypoints) < 2:
        raise ValueError(f"Trajectory needs ≥2 waypoints, got {len(waypoints)}")

    obj_type = records[0].get("object_type", "car")
    return Trajectory(name=name, waypoints=waypoints, object_type=obj_type)


def _parse_simple_format(name: str, raw: list[dict], carla_map: carla.Map) -> Trajectory:
    waypoints: list[Waypoint] = []
    for r in raw:
        try:
            t = float(r["t"])
            lat = float(r["lat"])
            lon = float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        loc = gps_to_carla(carla_map, lat, lon)
        waypoints.append(Waypoint(t=t, location=loc))

    waypoints.sort(key=lambda w: w.t)
    if len(waypoints) < 2:
        raise ValueError(f"Trajectory needs ≥2 waypoints, got {len(waypoints)}")
    # Normalise so first waypoint is at t=0
    t0 = waypoints[0].t
    for w in waypoints:
        w.t -= t0
    return Trajectory(name=name, waypoints=waypoints, object_type="car")


# ── Filesystem registry ─────────────────────────────────────────────────

# Bundled / uploaded trajectory storage. Lives next to the bridge package
# so it ships with the app (matches the pattern used by `scenes/`).
BRIDGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRAJECTORIES_DIR = os.path.join(BRIDGE_ROOT, "trajectories")


def _ensure_dir() -> None:
    os.makedirs(TRAJECTORIES_DIR, exist_ok=True)


def list_trajectory_files() -> list[dict]:
    """Return basic metadata for every trajectory JSON on disk."""
    _ensure_dir()
    out: list[dict] = []
    for fname in sorted(os.listdir(TRAJECTORIES_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(TRAJECTORIES_DIR, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            sample_count = len(data) if isinstance(data, list) else 0
        except Exception:
            sample_count = 0
        out.append({"file": fname, "samples": sample_count})
    return out


def load_trajectory_file(filename: str) -> list:
    """Read a trajectory JSON file. Raises FileNotFoundError if missing."""
    if "/" in filename or filename.startswith(".."):
        raise ValueError(f"Invalid trajectory filename: {filename}")
    fpath = os.path.join(TRAJECTORIES_DIR, filename)
    if not os.path.isfile(fpath):
        raise FileNotFoundError(f"Trajectory not found: {filename}")
    with open(fpath) as f:
        return json.load(f)


def save_trajectory_file(filename: str, data: list) -> str:
    """Persist an uploaded trajectory under TRAJECTORIES_DIR. Returns the path."""
    _ensure_dir()
    if "/" in filename or filename.startswith(".."):
        raise ValueError(f"Invalid trajectory filename: {filename}")
    if not filename.endswith(".json"):
        filename = f"{filename}.json"
    fpath = os.path.join(TRAJECTORIES_DIR, filename)
    with open(fpath, "w") as f:
        json.dump(data, f)
    return fpath


# ── Player ──────────────────────────────────────────────────────────────


class TrajectoryPlayer:
    """Plays one trajectory at a time as a physics-driven CARLA vehicle.

    Lifecycle:
        player.load_from_file(name)          # parse + cache trajectory
        player.start(vehicle_blueprint=...)  # spawn vehicle, begin playback
        # tick() called from drive_main's tick loop after world.tick()
        player.stop()                        # destroy vehicle, reset state
    """

    # Pure-pursuit + PID gains. Tuned for ~10–15 m/s urban traffic.
    LOOKAHEAD_GAIN = 1.5     # Ld = LOOKAHEAD_GAIN * speed, clamped
    LOOKAHEAD_MIN = 3.0
    LOOKAHEAD_MAX = 15.0
    PID_KP = 0.6
    PID_KI = 0.1
    PID_KD = 0.05
    INTEGRAL_CLAMP = 2.0
    MAX_SPEED_MS = 30.0
    DRIFT_WARN_M = 8.0
    STOP_VELOCITY_MS = 0.2

    def __init__(self, world: carla.World, carla_map: carla.Map):
        self._world = world
        self._map = carla_map
        self.trajectory: Optional[Trajectory] = None
        self.vehicle: Optional[carla.Vehicle] = None

        self._t_start: Optional[float] = None
        self._integral_v_err = 0.0
        self._last_v_err = 0.0
        self._finished = False

        # Bicycle-model parameters; refined from the actual physics control
        # of the spawned vehicle when possible.
        self._wheelbase = 2.5
        self._max_steer_rad = math.radians(70)

    # ── Lifecycle ──────────────────────────────────────────────────────

    def load(self, trajectory: Trajectory) -> None:
        self.trajectory = trajectory

    def load_from_file(self, filename: str) -> Trajectory:
        raw = load_trajectory_file(filename)
        traj = parse_trajectory(filename, raw, self._map)
        self.trajectory = traj
        return traj

    def start(self, vehicle_blueprint: str = "vehicle.tesla.model3") -> dict:
        if self.trajectory is None or len(self.trajectory.waypoints) < 2:
            raise RuntimeError("No trajectory loaded")
        if self.vehicle is not None:
            raise RuntimeError("Trajectory already playing — stop it first")

        bp_lib = self._world.get_blueprint_library()
        bps = bp_lib.filter(vehicle_blueprint) or bp_lib.filter("vehicle.tesla.model3")
        if not bps:
            raise RuntimeError("No vehicle blueprint available")
        bp = bps[0]
        try:
            bp.set_attribute("role_name", "trajectory")
        except Exception:
            pass

        wp0 = self.trajectory.waypoints[0]
        wp1 = self.trajectory.waypoints[1]
        yaw_deg = math.degrees(math.atan2(
            wp1.location.y - wp0.location.y,
            wp1.location.x - wp0.location.x,
        ))
        spawn_loc = carla.Location(x=wp0.location.x, y=wp0.location.y, z=wp0.location.z + 0.5)
        transform = carla.Transform(spawn_loc, carla.Rotation(yaw=yaw_deg))

        actor = self._world.try_spawn_actor(bp, transform)
        if actor is None:
            raise RuntimeError("Failed to spawn trajectory vehicle (location blocked?)")
        self.vehicle = actor

        self._refine_bicycle_params(actor)
        self._t_start = self._world.get_snapshot().timestamp.elapsed_seconds
        self._integral_v_err = 0.0
        self._last_v_err = 0.0
        self._finished = False

        logger.info(
            "Trajectory '%s' started: %d waypoints, %.1fs duration, vehicle_id=%d",
            self.trajectory.name, len(self.trajectory.waypoints),
            self.trajectory.duration, actor.id,
        )
        return {
            "vehicle_id": actor.id,
            "duration": round(self.trajectory.duration, 2),
            "waypoints": len(self.trajectory.waypoints),
            "name": self.trajectory.name,
        }

    def stop(self) -> dict:
        had_vehicle = self.vehicle is not None
        vehicle_id = self.vehicle.id if had_vehicle else None
        if self.vehicle is not None:
            try:
                self.vehicle.destroy()
            except Exception as e:
                logger.warning("Trajectory vehicle destroy failed: %s", e)
            self.vehicle = None
        self._t_start = None
        self._finished = False
        if had_vehicle:
            logger.info("Trajectory stopped (vehicle_id=%s)", vehicle_id)
        return {"stopped": had_vehicle}

    # ── Tick ───────────────────────────────────────────────────────────

    def tick(self) -> None:
        """Compute and apply one frame of control. Called from the tick loop."""
        if self.vehicle is None or self.trajectory is None or self._t_start is None:
            return

        snapshot = self._world.get_snapshot()
        t_elapsed = snapshot.timestamp.elapsed_seconds - self._t_start

        if t_elapsed >= self.trajectory.duration:
            # Past the end: brake to a stop, then idle.
            self.vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            if not self._finished and self._is_stopped():
                self._finished = True
                logger.info("Trajectory '%s' completed", self.trajectory.name)
            return

        wps = self.trajectory.waypoints
        i = self._bracket_index(t_elapsed)
        wp_i, wp_j = wps[i], wps[i + 1]
        seg_dt = max(1e-6, wp_j.t - wp_i.t)
        p = max(0.0, min(1.0, (t_elapsed - wp_i.t) / seg_dt))

        target_pos = self._lerp(wp_i.location, wp_j.location, p)
        seg_d = math.hypot(
            wp_j.location.x - wp_i.location.x,
            wp_j.location.y - wp_i.location.y,
        )
        target_v = min(self.MAX_SPEED_MS, seg_d / seg_dt)

        veh_tf = self.vehicle.get_transform()
        veh_loc = veh_tf.location
        veh_vel = self.vehicle.get_velocity()
        cur_v = math.hypot(veh_vel.x, veh_vel.y)

        # ── Steering: pure pursuit ──
        Ld = max(self.LOOKAHEAD_MIN, min(self.LOOKAHEAD_MAX, self.LOOKAHEAD_GAIN * cur_v))
        lookahead = self._lookahead_point(i, p, Ld)
        steer = self._pure_pursuit_steer(veh_tf, lookahead)

        # ── Throttle / brake: PID on velocity ──
        v_err = target_v - cur_v
        dt = 0.05  # matches drive_main tick_loop target_dt
        self._integral_v_err = max(
            -self.INTEGRAL_CLAMP,
            min(self.INTEGRAL_CLAMP, self._integral_v_err + v_err * dt),
        )
        deriv = (v_err - self._last_v_err) / dt
        self._last_v_err = v_err
        u = (
            self.PID_KP * v_err
            + self.PID_KI * self._integral_v_err
            + self.PID_KD * deriv
        )
        if u >= 0:
            throttle, brake = max(0.0, min(1.0, u)), 0.0
        else:
            throttle, brake = 0.0, max(0.0, min(1.0, -u))

        # Drift telemetry — useful for tuning, not corrective in B-lite.
        d_drift = math.hypot(target_pos.x - veh_loc.x, target_pos.y - veh_loc.y)
        if d_drift > self.DRIFT_WARN_M:
            logger.debug(
                "Trajectory drift %.1fm at t=%.1fs (target_v=%.1f, cur_v=%.1f)",
                d_drift, t_elapsed, target_v, cur_v,
            )

        self.vehicle.apply_control(carla.VehicleControl(
            steer=steer, throttle=throttle, brake=brake,
        ))

    # ── Status ─────────────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self.vehicle is not None

    def status(self) -> dict:
        if self.vehicle is None or self._t_start is None or self.trajectory is None:
            return {"active": False}
        snap = self._world.get_snapshot()
        t_elapsed = snap.timestamp.elapsed_seconds - self._t_start
        return {
            "active": True,
            "name": self.trajectory.name,
            "elapsed": round(t_elapsed, 2),
            "duration": round(self.trajectory.duration, 2),
            "vehicle_id": self.vehicle.id,
            "finished": self._finished,
        }

    # ── Internals ──────────────────────────────────────────────────────

    def _refine_bicycle_params(self, actor: carla.Vehicle) -> None:
        """Pull wheelbase + max steer from the vehicle's physics control."""
        try:
            phys = actor.get_physics_control()
            wheels = phys.wheels
            if len(wheels) >= 4:
                # Wheel positions are in cm (UE units).
                fx = (wheels[0].position.x + wheels[1].position.x) / 2.0
                rx = (wheels[2].position.x + wheels[3].position.x) / 2.0
                wb = abs(fx - rx) / 100.0
                if wb > 0.1:
                    self._wheelbase = wb
                self._max_steer_rad = math.radians(
                    max(w.max_steer_angle for w in wheels[:2])
                )
        except Exception as e:
            logger.debug("Bicycle param refine skipped: %s", e)

    def _bracket_index(self, t: float) -> int:
        """Find i such that wps[i].t <= t < wps[i+1].t. Linear scan; fine for ~hundreds."""
        wps = self.trajectory.waypoints
        for i in range(len(wps) - 1):
            if wps[i].t <= t < wps[i + 1].t:
                return i
        return len(wps) - 2

    def _pure_pursuit_steer(
        self, veh_tf: carla.Transform, lookahead: carla.Location,
    ) -> float:
        veh_loc = veh_tf.location
        dx = lookahead.x - veh_loc.x
        dy = lookahead.y - veh_loc.y
        yaw = math.radians(veh_tf.rotation.yaw)
        # Rotate world delta into vehicle frame: x = forward, y = left
        local_x = math.cos(yaw) * dx + math.sin(yaw) * dy
        local_y = -math.sin(yaw) * dx + math.cos(yaw) * dy
        # If the lookahead is behind, clamp forward so we still curve toward it
        local_x = max(local_x, 0.5)
        Ld_actual_sq = local_x * local_x + local_y * local_y
        steer_rad = math.atan2(2.0 * self._wheelbase * local_y, max(Ld_actual_sq, 0.25))
        return max(-1.0, min(1.0, steer_rad / self._max_steer_rad))

    def _lookahead_point(
        self, seg_i: int, seg_p: float, Ld: float,
    ) -> carla.Location:
        """Walk along the path from segment (seg_i, seg_p) until cumulative
        forward distance ≥ Ld; return the interpolated point."""
        wps = self.trajectory.waypoints
        wp_i = wps[seg_i].location
        wp_j = wps[seg_i + 1].location
        prev = self._lerp(wp_i, wp_j, seg_p)
        accum = 0.0
        for k in range(seg_i + 1, len(wps)):
            nxt = wps[k].location
            d = math.hypot(nxt.x - prev.x, nxt.y - prev.y)
            if accum + d >= Ld:
                frac = (Ld - accum) / max(1e-6, d)
                return self._lerp(prev, nxt, frac)
            accum += d
            prev = nxt
        return prev

    @staticmethod
    def _lerp(a: carla.Location, b: carla.Location, p: float) -> carla.Location:
        return carla.Location(
            x=a.x + p * (b.x - a.x),
            y=a.y + p * (b.y - a.y),
            z=a.z + p * (b.z - a.z),
        )

    def _is_stopped(self) -> bool:
        if self.vehicle is None:
            return True
        v = self.vehicle.get_velocity()
        return math.hypot(v.x, v.y) < self.STOP_VELOCITY_MS
